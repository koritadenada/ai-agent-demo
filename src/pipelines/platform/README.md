# Platform data pipeline

Turns the files AWS DMS writes to S3 into one current, queryable table per source table.

```
DMS files (S3) -> bronze streaming table -> <table>_changes view -> silver streaming table
                  change log, as received   prepares each change    current state (or history)
```

## Why the view

AUTO CDC reads from a table or view name, not from a query, so any preparation has to sit in a view. It adds
the ordering key (`_phase`, `_version`, `_commit_ts`) and the neutral column names. It is temporary: nothing is
stored and nothing is processed twice.

## Why a second streaming table

Bronze only appends: every change is a new row, so one source row can appear many times. Silver is the target
of AUTO CDC, which updates, deletes and keeps history in place, so it needs its own table. Keeping bronze
untouched also means silver can be rebuilt from it at any time.

## Full load and CDC

| What lands from DMS | How the pipeline handles it |
|---|---|
| **Full load** (`LOAD00000001.parquet` per table) | Read into bronze like any other file. Every row is `Op = I`, and a missing `Op` is also treated as I. AUTO CDC inserts them into silver |
| **Ongoing CDC** (timestamped files with I / U / D) | Appended to the same bronze table. AUTO CDC applies them in order: updates overwrite (SCD 1) or open a new version (SCD 2), and `Op = D` deletes |

So the initial snapshot and the change stream go through the same code path, with no separate backfill job.
Changes are ordered full load first, then by `version`,
then by commit time: DMS stamps full-load rows with the time it copied them, so a change committed while the
load was running can look older than the copy it replaces.

One limit: a second full load (a DMS reload) cannot remove rows deleted in between, because a snapshot has no
delete rows. If reloads are part of the process, compare consecutive snapshots instead (AUTO CDC from snapshot).

## How it runs

Auto Loader picks up new files only while the pipeline runs. The pipeline is triggered: each run processes the
new files since the last run, then stops. Something has to start it:

| Option | What starts it | Freshness | Cost |
|---|---|---|---|
| Continuous pipeline | Nothing, it never stops | Minutes | Highest: compute runs all day and night |
| Triggered pipeline + job | A schedule or a file-arrival trigger | Hourly or on arrival | Pay per run |
| One pipeline for everything | The same, one task | Same | One start-up per run, but one large graph that is hard to read |

Here it runs from the `portcall-refresh` job (`resources/refresh.job.yml`). The job starts the runs, and it
coordinates the three pipelines in order: platform data first (the documents need its expense vocabulary), then
documents, then gold, which needs both. Each pipeline keeps a small graph about one thing, and the job is the
one place that shows the order and the status of every run.
