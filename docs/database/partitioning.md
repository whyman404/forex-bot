# Partitioning Strategy — Forex/Crypto Trading Bot

> Range partitioning, retention, and maintenance plan
> **Author:** Mnemosyne Rin
> **Created:** 2026-06-14
> **PostgreSQL:** 16
> **Recommended extension:** `pg_partman` 5.x (optional but reduces ops burden)

---

## 1. Why partition?

Three tables grow with user activity and time. At Phase 3 scale (~1,000 active users) we project:

| Table        | Rows/month (P3) | Year-end size | Hot read window |
|--------------|-----------------|---------------|-----------------|
| signals      | ~6 M            | ~72 M         | last 7-30 days  |
| trades       | ~1.5 M          | ~18 M         | last 90 days    |
| audit_log    | ~900 K          | ~11 M         | last 30 days; full retained 7y |

Without partitioning:
- Indexes balloon (a 70M-row btree is workable but heavy at writes).
- Vacuum/autovacuum windows lengthen on a single huge table.
- Cold rows (years old) sit in the same heap as hot rows — wastes cache.

**With monthly range partitions:**
- Hot partitions stay small; indexes fit in RAM.
- Pruning (`enable_partition_pruning = on`, default) makes time-windowed queries scan only relevant partitions.
- Dropping a partition = instant retention enforcement, no `DELETE` lock storm.
- Per-partition `VACUUM`/`ANALYZE` runs faster and parallelizes.

---

## 2. Partition keys

| Table       | Partition by    | Granularity | Rationale |
|-------------|-----------------|-------------|-----------|
| signals     | `ts`            | monthly     | `ts` is the signal time used in every read query (chart, replay). |
| trades      | `created_at`    | monthly     | `created_at` is monotonic at insert; `entry_at` could differ by milliseconds and we'd lose partition affinity on broker ticks. |
| audit_log   | `created_at`    | monthly     | Append-only; all queries time-windowed. |

**Note on PK constraint:** PostgreSQL requires the partition key to be part of any UNIQUE / PRIMARY KEY constraint on a partitioned table. Hence composite PKs `(id, ts)` / `(id, created_at)`. Applications still treat `id` as the logical identifier; the partition key is implicit in any row insert/update.

---

## 3. Naming convention

```
<table>_y<YYYY>_m<MM>          e.g. signals_y2026_m06
<table>_default                 catch-all for misrouted rows; should remain EMPTY
```

A non-empty `_default` partition is an alert condition (means partition-rotation cron failed to provision the next month).

---

## 4. Initial provisioning

The `0001_initial` migration provisions:

- `_default` catch-all
- 3 monthly partitions covering the launch window: `2026_m06`, `2026_m07`, `2026_m08`

Future months are added by the **partition maintenance job** (section 6).

---

## 5. Retention policy (drop-old partitions)

| Table       | Hot retention (online) | Cold retention (archived) | Hard drop |
|-------------|------------------------|---------------------------|-----------|
| signals     | 24 months              | export to ClickHouse / S3 parquet at 24m | drop partition at 24m after archive verified |
| trades      | indefinite             | move to `trades_archive` schema after 36m; only `closed` status | never drop (financial regulator audit) |
| audit_log   | 12 months              | export to S3 (WORM bucket) after 12m | drop partition at 84m (7-year retention end) |

Retention dropping uses `ALTER TABLE ... DETACH PARTITION` + `DROP TABLE` so the parent table is never locked.

---

## 6. Maintenance job

Two options. Pick **Option A** for an MVP; promote to **Option B** if ops want hands-off.

### Option A — Custom monthly cron (initial)

A SQL function `create_monthly_partitions(months_ahead INT)` is run by a cron job once a week:

```sql
CREATE OR REPLACE FUNCTION create_monthly_partitions(months_ahead INT DEFAULT 3)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    base_month DATE := date_trunc('month', now())::date;
    target_month DATE;
    next_month DATE;
    partition_name TEXT;
    parent_table TEXT;
    parents TEXT[] := ARRAY['signals','trades','audit_log'];
BEGIN
    FOREACH parent_table IN ARRAY parents LOOP
        FOR i IN 0..months_ahead LOOP
            target_month := base_month + (i || ' months')::interval;
            next_month   := target_month + INTERVAL '1 month';
            partition_name := format('%s_y%s_m%s',
                parent_table,
                to_char(target_month, 'YYYY'),
                to_char(target_month, 'MM'));
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
                partition_name, parent_table,
                target_month::timestamptz, next_month::timestamptz);
        END LOOP;
    END LOOP;
END;
$$;
```

**Cron schedule:** every Sunday 02:00 UTC (`SELECT create_monthly_partitions(3);`).
**Alert:** if any default partition has rows: `SELECT count(*) FROM signals_default;` > 0 -> PagerDuty.

### Option B — `pg_partman` (recommended for Phase 3)

```sql
CREATE EXTENSION pg_partman;
SELECT partman.create_parent(
    p_parent_table => 'public.signals',
    p_control => 'ts',
    p_interval => '1 month',
    p_premake => 3
);
-- Repeat for trades, audit_log.
-- Schedule:  SELECT partman.run_maintenance_proc();  every hour via pg_cron.
```

`pg_partman` also handles **retention drop** out of the box via `retention` and `retention_keep_table` parameters.

---

## 7. Query patterns benefiting from pruning

```sql
-- Pruning: only signals_y2026_m06 partition is scanned
SELECT * FROM signals
WHERE strategy_instance_id = $1
  AND ts >= '2026-06-01' AND ts < '2026-07-01'
ORDER BY ts DESC
LIMIT 100;

-- Pruning + index scan in current partition
SELECT count(*) FROM trades
WHERE strategy_instance_id = $1
  AND status = 'open'
  AND created_at >= now() - INTERVAL '1 day';
```

**Anti-pattern (will scan all partitions):**

```sql
-- BAD: no time predicate; this falls back to seq-scan of every partition
SELECT * FROM signals WHERE strategy_instance_id = $1 ORDER BY ts DESC LIMIT 10;
```

For the unbounded "last N for this instance" case, the application should default to `ts >= now() - INTERVAL '90 days'` to constrain pruning, or, if older lookback is required, accept the cost and explicitly opt-in.

---

## 8. Archive workflow (signals + audit_log)

```
[ partition older than retention ]
        |
        v
   DETACH PARTITION (no parent lock)
        |
        v
   pg_dump -t signals_y2024_m06 -F c > /archive/signals_y2024_m06.dump
   psql -c "COPY signals_y2024_m06 TO PROGRAM 'gzip > /archive/.../parquet'"
        |
        v
   Verify file checksum + row count == pg row count
        |
        v
   DROP TABLE signals_y2024_m06
```

Archive runs monthly on the 5th. We keep parquet exports in S3 with object-lock (WORM) for compliance.

---

## 9. Operational guardrails

- **VACUUM ANALYZE per partition:** autovacuum config tightened on hot partition only.
- **Monitoring:** Grafana panel of `pg_relation_size('signals_y...')` per partition.
- **Alert:** `_default` partition row count > 0 (means future partition wasn't created).
- **Index inheritance:** PG16 inherits indexes from the parent; do not create local indexes per partition unless they differ by partition.
- **CHECK constraints inherited:** all CHECKs on the parent apply to partitions, no need to redefine.

---

## 10. Migration impact

- Adding a new column on a partitioned parent applies to all partitions atomically — but for very wide partitions consider `ADD COLUMN ... DEFAULT NULL` (constant default) which is metadata-only in PG11+.
- Adding an index on the parent will build it on every partition — schedule during low traffic; use `CREATE INDEX CONCURRENTLY` per partition for zero-lock.

---

## 11. Capacity numbers (sanity-check)

| Partition size at P3 | Compressed (TOAST + heap) | Index size | Total RAM-required (hot) |
|----------------------|---------------------------|------------|--------------------------|
| signals (month)      | ~1.2 GB                   | ~600 MB    | ~1.8 GB                  |
| trades  (month)      | ~400 MB                   | ~200 MB    | ~600 MB                  |
| audit_log (month)    | ~250 MB                   | ~120 MB    | ~370 MB                  |

The current monthly hot working set sits comfortably under 4 GB — well within a 16 GB shared_buffers + page cache budget on the recommended VPS.

---

## 12. References

- PostgreSQL 16 docs — Table Partitioning
- pg_partman 5 README
- Daedalus ADR-003 — PostgreSQL 16 stack choice
- `data-retention.md` — retention windows
