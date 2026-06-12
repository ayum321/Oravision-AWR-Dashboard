"""Waits for the OraVision server then opens the browser once.

Port passed as argv[1]. Verifies the server identity by checking the /api
endpoint returns the OraVision app signature — this prevents opening a
different project's dashboard that happens to be on a nearby port.
"""
import json
import sys
import time
import webbrowser
from urllib.request import urlopen
from urllib.error import URLError

import os

BASE_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
PORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".oravision_port")


def read_actual_port():
    """Read the port that _start_server.py actually bound to."""
    try:
        with open(PORT_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None


def is_oravision(port: int) -> bool:
    """Check if the server on this port is actually OraVision AWR Pro."""
    try:
        resp = urlopen(f"http://127.0.0.1:{port}/api", timeout=1)
        data = json.loads(resp.read())
        return "OraVision" in data.get("app", "")
    except Exception:
        return False


# Poll for up to 30 seconds (60 × 0.5s)
# Priority: check the port file first (written by _start_server.py),
# then fall back to scanning the range
for _ in range(60):
    # Check port file first — this is the ACTUAL port the server bound to
    actual = read_actual_port()
    if actual and is_oravision(actual):
        webbrowser.open(f"http://localhost:{actual}")
        sys.exit(0)
    # Fallback: scan range starting from base port
    for port in range(BASE_PORT, BASE_PORT + 10):
        if port == actual:
            continue  # already checked above
        if is_oravision(port):
            webbrowser.open(f"http://localhost:{port}")
            sys.exit(0)
    time.sleep(0.5)
