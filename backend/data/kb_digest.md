# KB Digest — Expert Incident Knowledge Base

This file trains the AWR dashboard with **real fixes** from the team. When the
dashboard flags a bottleneck (a regressed `SQL_ID`, a hot wait event/class, or a
bottleneck class), it cross-references the incidents below and shows how the same
symptom was actually resolved before — and by whom.

The Outlook digest puller appends new incidents here. You can also paste them by
hand. The dashboard hot-reloads this file automatically (no restart needed).

## How to add an incident

Copy the template below into the **Incidents** section and fill it in. Every
field is optional, but include at least one of `sql_id`, `wait`, `bottleneck`,
`segment`, or `tags` so it can be matched. Comma-separate multiple values.

```markdown
## <short title of the problem>
- db: PRNEI77C
- date: 2025-03
- engineer: Rangadu
- bottleneck: Concurrency        # CPU | I/O | Concurrency | Commit | Cluster | Network | Mixed
- wait: latch: shared pool, library cache: mutex X
- sql_id: 7xkq9z2pksvwa, a1b2c3d4e5f6g
- segment: SCPOMGR.LANEEXCEPTION_IDX1
- symptom: DB time up 5x, hard-parse storm during the batch window
- root_cause: Literal SQL flooding the shared pool (no bind variables)
- fix: cursor_sharing=FORCE on the batch service; bound the offending SQL; pinned packages
- outcome: DB time -62%, latch waits cleared
- tags: hard-parse, shared-pool, batch
```

Matching weights: `SQL_ID` exact = strongest, then `wait` event/class, then
`bottleneck` class, then `segment`. Higher combined score ranks first.

---

# Incidents

<!--
  Generated from knowledge_base.jsonl by tools/build_digest.py.
  Grouped by engineer. Re-run after exporting more e-mails; it dedups.
  Contributors: Rangadu · Zafar · Sukhamoy · Virendra · Ayush
-->

## SC-FAIL_ALTRIA_DNF_2019_PROD_GVA3300-WKLY-SALES_TABLEAU Failed
- db: PRBD121403001
- date: 2026-05
- engineer: Rangadu
- bottleneck: Concurrency
- wait: enq: TX - row lock contention
- sql_id: a9wzhkwz8v348, 8ut3qswcum3ry
- fix: create index SRE_SYSTEM_ALERT_T1 on SRE_SYSTEM_ALERT (NODE_ID); Please review and perform the SRE cleanup in coordination with the Platform Support team, as necessary.
- tags: batch, index

## Under Armour Weekend batch status - 24-May-2026
- date: 2026-05
- engineer: Rangadu
- bottleneck: I/O
- sql_id: gqmyhpj0kd7p6, cqy3jqhw52200, cxgk4bkakvj63
- root_cause: We observed an increase in the runtime of a few SQLs due to a higher number of executions and elevated I/O waits.
- fix: To avoid execution plan deviations, we recommend gathering statistics on the VEHICLELOADLINE table after data population or modification. Please work with DBA team to pin below plans. SQL ID Plan hash value
- tags: batch, plan, index

## AZ S.p.A SLA misses last few days
- date: 2026-06
- engineer: Rangadu
- root_cause: The increase in runtime appears to be proportional to this growth in workload. I was unable to identify the number of rows processed by this SQL, either because no rows were processed or because the information was not captured in the available database history.
- fix: Is there a specific reason for gathering statistics on these tables while they are empty? Since we locked the table PRICESCENARIODFUEXCEPTION , the job UPD_STATS_OUTPUTTABLES will fail while gathering stats for PRICESCENARIODFUEXCEPTION table. We need to comment that gathering stats for table PRICESCENARIODFUEXCEPTION we need to add unlock stats before gathering ..
- tags: batch, plan, stats, index

## OnSemi Batch Performance - JIRA ASRE-12259
- db: prbc651503011
- date: 2026-06
- engineer: Rangadu
- bottleneck: I/O
- sql_id: 6dfwd2x7gs12w, 31k2a20kyunqa, 9xy5xutupdp0r
- segment: SCPOMGR.UDT_SKUPROJSTATIC_ARCH, SCPOMGR.UDT_OP_INDDMDLINK
- symptom: Support team to further provide list of non GMP jobs that has been taking long time since Jan. SQL ID 6dfwd2x7gs12w is experiencing execution plan deviations.
- root_cause: Below DELETE statement took approximately 3.7 hours to complete and appears to be part of the post script. Meanwhile, could you please create an index on UDT_SKUPROJSTATIC_ARCH(RECORD_DATE_TIME) in TEST instance and check the performance in lower environment (as the table is huge(501M), we need to ensure no DMLs gettin
- fix: If any specified plan hash value is not available in TEST instance, you can ask DBA team to import it from PROD . Parallel DML has been enabled for the post-processing phase of this job. Similar optimizations (Parallel DML and hints) have been implemented for this job . We are yet to pin the SQL ID for the optimal execution plan in TEST.
- outcome: Good to hear that suggested changes have improved runtime of the jobs. Yes, reducing runtime of ON_SP_STORE_SKUPROJ_SNOE_CIII job would improve other IO/DB intensive processes running concurrently.
- tags: batch, plan, stats, index, purge, archive

## SC-LONG_SMUCKERS_ESP_2022_PROD_ESP_FQ_SUP_DMD_Links_W is running long on prbb391526011.jdadelivers.
- db: prbb391526011
- date: 2026-06
- engineer: Rangadu
- bottleneck: Concurrency
- segment: SCPOMGR.SKUPROJSTATIC_PK
- symptom: SRE related SQLs were experiencing concurrency waits(buffer busy) induced by slow archive processes. Please check with the DBA team to confirm whether any archive destination changes, space constraints, or other issues caused the slow archives.
- root_cause: This is resulting in node failures due to unique constraint violations and is contributing to increased runtime and job failures. In the daily batch ESP_Store_SKU_Proj_Daily_SS_D_ESP has failed due to unique constraint issue and this job also failed on 31st Sun as part of daily batch.
- fix: update WWFMGR.sre_global_property set value=60 where name ='GROUPMGRTIMEOUTSECS'; update WWFMGR.sre_global_property set value=120 where name ='UNASSIGNEDNODEDUR'; update WWFMGR.sre_global_property set value=3 where name ='MAINTENANCESECS'; Please disable below auto clients.
- tags: batch, plan, archive

## ph_esp_uncons_global_scenario_load long run
- date: 2026-06
- engineer: Rangadu
- bottleneck: Concurrency
- segment: SIM_INDDMDLINK.CUST
- symptom: Since the thread timeout was configured to 40 minutes, the initial SQL executions were terminated upon reaching the timeout threshold, triggering a second execution.
- fix: I would suggest checking and avoid running these jobs concurrently.
- tags: plan

## SC-LONG_PEPSICO_SNOP_PROD_PEP_LATAM_SOP_UPDATE_WFALL_CUBE is running long on dlpimprdapp5v.jdadeliv
- date: 2026-06
- engineer: Zafar
- sql_id: 8wpxq2gfhjc98
- segment: ABPPMGR_SOP.MD_CUBE_WATERFALL, ABPPMGR_SOP.MD_CUBE_AT_LEAF_LEVEL, ABPPMGR_SOP.DIMENSION_MEMBER_RELATIONSHIP
- symptom: There was no plan deviation for the SQL and it was running with optimal plan. It will slow the currently running SQL.
- root_cause: Last run was around 11 hours today it was slow down due to parallel gather stats. Degree of Parallelism is 16 because of hint
- fix: I see you had started a gather stats for MD_CUBE_WATERFALL in parallel not sure what was the intention. I see you have deleted the stats of MD_CUBE_WATERFALL before starting the gather stats it is not needed as gathering the stats will update the stats and there is no explicit deletion of stats are needed specially for large tables in case the gather stats fails it will leave the table without the stats. Gather stats was running for over 2 hours in parallel with the actual SQL. Use the below gather stats options fo
- tags: batch, plan, stats, index, temp

## SC-LONG_WICKES_LDE_PROD_LOAD_TRANSMODE_S_F is running long on prbc321426001.jdadelivers.com Please
- db: prbc321426001
- date: 2026-06
- engineer: Zafar
- sql_id: 6pg97b7tv41kk
- segment: SCPOMGR.TRANSMODE, IGPMGR.INTUPS_TRANSMODE
- symptom: The DELETE statement on table TRANSMODE is taking significantly more time than expected today
- root_cause: The existing delete approach is not optimized for scenarios where a master table has multiple child dependencies and requires large-scale cascading deletion handling
- fix: The Performance Engineering (PE) team has developed the MDD (Master Delete Dependency) tool under UtilityHubPro. The tool generates an optimized deletion script for master tables with complex parent-child relationships, ensuring deletion is performed in a controlled and efficient manner
- tags: batch, plan, index, purge
