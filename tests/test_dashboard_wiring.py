"""Regression tests for dashboard data wiring and SQL row metrics."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import main  # noqa: E402
from services.data_source import clear_uploaded_data, store_uploaded_data  # noqa: E402
from services.html_parser import _parse_sql_stats, normalize_parsed_data  # noqa: E402


class SqlRowsProcessedTests(unittest.TestCase):
    def test_rows_processed_is_derived_from_rows_per_exec(self) -> None:
        html = """
        <html><body>
        <table summary="sql ordered by elapsed time">
          <tr>
            <th>SQL Id</th><th>Elapsed Time (s)</th><th>Executions</th>
            <th>Elapsed per Exec (s)</th><th>%Total</th><th>SQL Text</th>
          </tr>
          <tr>
            <td>abc123def4567</td><td>10</td><td>20</td><td>0.5</td><td>2</td><td>select * from dual</td>
          </tr>
        </table>
        <table summary="sql ordered by executions">
          <tr><th>SQL Id</th><th>Executions</th><th>Rows per Exec</th></tr>
          <tr><td>abc123def4567</td><td>20</td><td>15.5</td></tr>
          <tr><td>xyz987uvw6543</td><td>10</td><td>3</td></tr>
        </table>
        </body></html>
        """

        soup = BeautifulSoup(html, "html.parser")
        entries, _ = _parse_sql_stats(soup)
        by_id = {entry["sql_id"]: entry for entry in entries}

        self.assertEqual(by_id["abc123def4567"]["rows_per_exec"], 15.5)
        self.assertEqual(by_id["abc123def4567"]["rows_processed"], 310)
        self.assertEqual(by_id["xyz987uvw6543"]["rows_processed"], 30)

        model = normalize_parsed_data({"sql_stats": entries})
        normalized = {sql.sql_id: sql for sql in model.sql_stats}
        self.assertEqual(normalized["abc123def4567"].rows_processed, 310)
        self.assertEqual(normalized["abc123def4567"].rows_per_exec, 15.5)


class DashboardWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_uploaded_data()
        self.client = TestClient(main.app)

        self.good_data = {
            "db_name": "GOOD_REAL",
            "instance": "GOOD1",
            "host": "host-good",
            "release": "19c",
            "cpus": 4,
            "memory_gb": 32,
            "begin_snap": 1,
            "end_snap": 2,
            "begin_time": "2026-04-23 10:00:00",
            "end_time": "2026-04-23 11:00:00",
            "elapsed_min": 60,
            "db_time_min": 90,
            "efficiency": {"buffer_cache_hit_pct": 99.1, "soft_parse_pct": 97.2},
            "load_profile": [{"stat_name": "Logical Reads", "per_sec": 10, "per_txn": 1}],
            "wait_events": [],
            "sql_stats": [
                {
                    "sql_id": "slow000000001",
                    "elapsed_time_secs": 20,
                    "cpu_time_secs": 5,
                    "disk_reads": 100,
                    "buffer_gets": 200,
                    "executions": 2,
                    "avg_elapsed_secs": 10,
                    "rows_processed": 40,
                    "rows_per_exec": 20,
                },
                {
                    "sql_id": "fast999999999",
                    "elapsed_time_secs": 5,
                    "cpu_time_secs": 2,
                    "disk_reads": 10,
                    "buffer_gets": 20,
                    "executions": 50,
                    "avg_elapsed_secs": 0.1,
                    "rows_processed": 500,
                    "rows_per_exec": 10,
                },
            ],
        }
        self.bad_data = {
            **self.good_data,
            "db_name": "BAD_REAL",
            "instance": "BAD1",
            "efficiency": {"buffer_cache_hit_pct": 88.0, "soft_parse_pct": 70.0},
            "sql_stats": [
                {
                    "sql_id": "bad1111111111",
                    "elapsed_time_secs": 30,
                    "cpu_time_secs": 10,
                    "disk_reads": 150,
                    "buffer_gets": 300,
                    "executions": 3,
                    "avg_elapsed_secs": 10,
                    "rows_processed": 42,
                    "rows_per_exec": 14,
                }
            ],
        }

        store_uploaded_data("uploaded_good", self.good_data)
        store_uploaded_data("uploaded_bad", self.bad_data)

    def tearDown(self) -> None:
        clear_uploaded_data()

    def test_overview_prefers_uploaded_period_data(self) -> None:
        response = self.client.get("/api/overview/good")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["source"], "uploaded_good")
        self.assertEqual(payload["db_info"]["db_name"], "GOOD_REAL")
        self.assertEqual(payload["kpis"]["soft_parse"], 97.2)
        self.assertEqual(payload["load_profile"][0]["stat_name"], "Logical Reads")

    def test_sql_endpoint_returns_rows_and_does_not_mutate_overview_order(self) -> None:
        sql_response = self.client.get("/api/sql/top/good?order_by=executions")
        self.assertEqual(sql_response.status_code, 200)
        sql_payload = sql_response.json()

        self.assertEqual(sql_payload["source"], "uploaded_good")
        self.assertEqual(sql_payload["sql_stats"][0]["sql_id"], "fast999999999")
        self.assertEqual(sql_payload["sql_stats"][0]["rows_processed"], 500)
        self.assertEqual(sql_payload["sql_stats"][0]["rows_per_exec"], 10)

        overview_response = self.client.get("/api/overview/good")
        overview_payload = overview_response.json()
        self.assertEqual(overview_payload["top_sql"][0]["sql_id"], "slow000000001")

    def test_compare_route_prefers_uploaded_pair(self) -> None:
        response = self.client.get("/api/compare/mock")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["sources"]["good"], "uploaded_good")
        self.assertEqual(payload["sources"]["bad"], "uploaded_bad")
        sql_regressions = payload["report"]["sql_regressions"]
        self.assertTrue(sql_regressions)
        self.assertIn("good_rows_processed", sql_regressions[0])
        self.assertIn("bad_rows_processed", sql_regressions[0])


if __name__ == "__main__":
    unittest.main()
