# Kafka/OOP/demo implementation and verification

Verified locally on 12 November 2026, branch `feature/s1-kafka-oop-bootstrap`,
starting from clean main commit `3760836`. No commit, push or merge was performed.

## Implemented phases

1. Audited local workspace/instructions, created the feature branch and ran the
   original 190 tests successfully against disposable PostgreSQL.
2. Added stable, transactional demo bootstrap: four dedicated meters, 14 previous
   complete UTC days, 1344 hourly readings and a tariff if none is active. Startup
   is opt-in demo behavior; existing dedicated history is adopted without backfill.
3. Introduced the profile ABC/Strategy design, frozen context/energy quantity,
   meaningful kWh addition and a generator used by actual simulation paths. Kept
   v1 deterministic live values and included-submeter semantics.
4. Added Kafka KRaft, topics, durable building-minute outbox, acknowledged producer,
   transactional consumer receipts and acknowledged dead-letter policy. Compose
   selects Kafka and replaces its previous direct worker.
5. Added Building Management; preserved Meter Management, all existing pages and
   styling; added pagination, distinct ID labels and required-meter confirmation.
6. Added optional paired inclusive UTC scenario dates. Baseline and modified prices
   use the same bounded S1 report; legacy no-date behavior and quality checks remain.
7. Ran automated suites, a fresh isolated real-broker workflow, outage/replay/DLQ
   and restart checks, then upgraded the original local stack without replacing data.

## OOP and delivery

`EnergyProfile.calculate_power(context)` is abstract. Electricity, HVAC, Lighting
and Solar profiles override it. `TelemetryGenerator` composes a read-only strategy
registry and dispatches polymorphically. `iter_readings()` yields measurements.
Frozen `ProfileContext` and `EnergyQuantity` protect values; `__add__` combines kWh
only and is used to check included submeter energy against gross consumption.
See the [implemented class diagram](s1-architecture.md).

The producer commits a frozen `TelemetryBatch` before publishing to
`energy.readings.raw`, keyed by building ID. All meter members share ordering.
Producer acknowledgment is required; pending batches survive failures and are
republished. Consumer ingestion and its receipt commit together before the source
offset. Exact replay returns the receipt; conflicting/changed-inventory/overlapping
batches never overwrite measurements. Permanent invalid events go to an acknowledged
DLQ before source commit. Database or DLQ failure leaves the source uncommitted.
This is **at-least-once delivery**, not distributed exactly-once processing.
[Detailed failure behavior](kafka.md).

## Executed checks and results

Commands below use the helper in the Docker guide. Tests create/drop only their
explicitly named disposable PostgreSQL database, not application tables.

```sh
# Original baseline, before implementation (old image):
dc run --rm --no-deps -T --pull never \
  --volume "$PWD/backend:/app/backend:ro" \
  --env DB_TEST_NAME=test_kafka_baseline --env OPENAI_API_KEY= \
  backend python backend/manage.py test config monitoring coach analysis --noinput
# 190 tests, OK.

# Final built release image, after upgrade:
dc exec -T -e DB_TEST_NAME=test_kafka_release -e OPENAI_API_KEY= \
  backend python backend/manage.py test config monitoring coach analysis --noinput
# Ran 227 tests in 6.020s; OK. Test database destroyed afterward.

# Host dashboard source mounted read-only, HTTP mocked:
dc run --rm --no-deps -T --pull never \
  --volume "$PWD/frontend:/app/frontend:ro" --env OPENAI_API_KEY= \
  backend python -m unittest discover -s frontend -p 'test_*.py'
# Ran 7 tests in 0.816s; OK.

dc exec -T backend python backend/manage.py check --database default
# System check identified no issues (0 silenced).
dc exec -T backend python backend/manage.py makemigrations --check --dry-run
# No changes detected.
dc exec -T backend python backend/manage.py migrate --plan
# No planned migration operations.
dc config --quiet
git diff --check
# Both successful, no errors.
```

An intermediate test run caught a command error-handling regression and an
incomplete new mock; both were fixed. Another new assertion initially expected
200 for successful recommendation creation; the existing API correctly returns
201. Existing tests were retained; final runs have no failures.

Runtime used Django 5.2.19 and PostgreSQL 18.6. Both the application image and
`apache/kafka:4.3.2` ran natively as arm64 on this machine.

### Fresh isolated acceptance

Created project `smart-energy-acceptance`, port 18000, with separate new PostgreSQL
and Kafka volumes. External OpenAI was explicitly disabled. Startup initialized
2026-10-29 through 2026-11-11, inclusive, with 1344 readings.

```sh
OPENAI_API_KEY= DOCKER_BACKEND_PORT=18000 docker compose --env-file .env.docker \
  -p smart-energy-acceptance up -d --build
python3 scripts/verify_demo.py --isolated-api http://127.0.0.1:18000/api
```

Actual script output:

```text
PASS: overview, seven-day forecast, rule-based recommendations/assessment, costs, report, dated scenario.
Created building=2, activated main/HVAC. Waiting for real completed Kafka interval...
PASS: Kafka persisted live batch. Deactivated HVAC; verifying main continues and history remains...
PASS: deactivation retains HVAC history and subsequent main-only Kafka telemetry continues.
{"demo_building_id": 1, "management_building_id": 2, "report_id": 1, "forecast_days": 7, "scenario_available": true}
```

Verified HTTP routes: building/meter create and PATCH, reading history and summary,
forecast, recommendation generation/assessment, cost, stored report, dated scenario.
For a -10% consumption scenario over those 14 days the API returned:

```json
{"available": true, "period_start": "2026-10-29", "period_end": "2026-11-11", "difference_net_cost_eur": -72.5}
```

Additional real-broker checks:

- Re-published a committed raw batch: consumer logged `already_processed`.
- Stopped only the isolated broker: publication timed out with the expected
  unacknowledged-publication failure; broker restoration resumed processing.
- Published schema version 99: consumer logged `dead_lettered`, and the actual
  dead-letter topic contained the source offset and validation reason.
- Normal full stop/start retained all 1373 pre-restart readings, both buildings,
  six meters, seven forecasts, two recommendations, execution log, tariff and
  report, with their original field values. Bootstrap returned `already_initialized`
  with zero new historical readings. New legitimate live rows can still be added.

Removed acceptance containers/network afterward using `down` **without -v**.
Both acceptance data volumes remain. Timing-controlled process-kill injection into
specific crash windows was not performed; receipt replay, rollback, concurrency,
normal restart and broker outage were tested as described above.

### Existing application preservation and upgrade

Stopped the old direct telemetry worker before starting the migration/bootstrap
chain. Kept the original PostgreSQL container and `smart-energy_postgres_data`.
Migration 0004 created only the two new auxiliary tables. Bootstrap adopted the
existing dedicated building with `created=0` and preserved the active tariff.

Compared every original row and field before/after: two buildings (including names),
eight meters, all 3748 readings present just before upgrade, seven forecasts,
12 recommendations, six request logs and the existing tariff were unchanged.
The earlier 3612-reading initial snapshot was also preserved. Private `.env` and
`.env.docker` hashes remained identical. No host PostgreSQL database was migrated.

The current database has **zero complete days for building #1**, whose partial
history was intentionally not repaired, and **14 complete days for building #2**.
Select building #2 for current forecast/historical scenario demonstrations. Fresh
installations receive full history for their dedicated demo building automatically.
Optional demo refresh fills only wholly empty days and never repairs partial days.

Final runtime: PostgreSQL, Kafka and API healthy; Kafka producer and consumer
running; migration, bootstrap and topic-init jobs exited successfully. Existing
port 8000 serves the upgraded app. The dashboard continues to run on the host.

## Every added or modified file

| File | Purpose |
| --- | --- |
| `.env.docker.example` | Demo-mode/image configuration examples, no credentials. |
| `compose.yaml` | Kafka/topics/bootstrap/consumer and ordered startup; retains PostgreSQL mount. |
| `requirements.txt` | Adds the Kafka Python client only. |
| `backend/monitoring/models.py` | Adds stable DemoDataset and durable TelemetryBatch. |
| `backend/monitoring/migrations/0004_demodataset_telemetrybatch.py` | Creates only those new tables; old migrations untouched. |
| `backend/monitoring/services/demo.py` | Safe identity, first-run history, tariff setup and explicit empty-day refresh. |
| `backend/monitoring/services/profiles.py` | ABC, four strategies, frozen value/context and streaming orchestration. |
| `backend/monitoring/services/generator.py` | Uses profiles; stages Kafka batches while preserving direct mode. |
| `backend/monitoring/services/kafka_pipeline.py` | Strict event contract, acknowledged publication, atomic processing, receipts and DLQ. |
| `backend/monitoring/management/commands/bootstrap_demo.py` | Explicit demo flag and optional refresh CLI. |
| `backend/monitoring/management/commands/setup_demo_inventory.py` | Reuses stable inventory recognition; still inventory-only. |
| `backend/monitoring/management/commands/run_telemetry.py` | Explicit direct/Kafka selection and outbox publication. |
| `backend/monitoring/management/commands/consume_telemetry.py` | Dedicated manual-commit consumer process. |
| `backend/monitoring/test_bootstrap_profiles.py` | OOP, deterministic fixtures, history, preservation and S2/S3 readiness tests. |
| `backend/monitoring/test_kafka_pipeline.py` | Schema, ack/retry/DLQ, inventory, conflict, rollback and PostgreSQL concurrency tests. |
| `backend/analysis/serializers.py` | Paired inclusive scenario date and finite-percentage validation. |
| `backend/analysis/services/scenarios.py` | Bounded shared aggregation, same period for both prices. |
| `backend/analysis/views.py` | Passes validated optional dates. |
| `backend/analysis/test_scenario_periods.py` | Complete/incomplete windows, gaps, alignment and legacy compatibility tests. |
| `frontend/app.py` | Building Management, pagination, confirmations and scenario date controls. |
| `frontend/test_app.py` | Seven Streamlit interaction tests with mocked HTTP. |
| `scripts/verify_demo.py` | Guarded port-18000 real-pipeline acceptance workflow. |
| `README.md` | Updated architecture, automatic startup and capabilities; preserves team/video. |
| `frontend/README.md` | Current pages, empty states and UI test command. |
| `docs/docker-development.md` | Exact safe setup, startup, logs, refresh and one-pipeline operations. |
| `docs/kafka.md` | Protocol, transaction/offset guarantees and remaining failure limits. |
| `docs/s1-architecture.md` | Code-linked explanation of every requested OOP concept and UML. |
| `docs/uml/s1-telemetry.mmd` | Implemented S1 class diagram source. |
| `docs/simulated-telemetry.md` | Profile semantics and direct/Kafka distinction. |
| `docs/energy-calculations.md` | Corrects historical bootstrap/consumer documentation. |
| `docs/s1-management-api.md` | Dashboard integration using existing inventory endpoints. |
| `docs/coach-analysis-api.md` | Inclusive date contract and example; optional OpenAI wording. |
| `docs/testing.md` | PostgreSQL suites, AppTest and safe isolated real-broker workflow. |
| `docs/implementation-verification.md` | This implementation/file/results record. |

## Start the system

Retain existing private configuration. For a fresh installation follow the
[secret-generation instructions](docker-development.md#first-setup), then:

```sh
dc() { docker compose --env-file .env.docker -p smart-energy "$@"; }
dc build backend
dc up -d
dc ps -a
# In a host virtual environment:
pip install -r frontend/requirements.txt
streamlit run frontend/app.py
```

The remaining limits are intentional and documented: synthetic heuristic profiles,
no battery or activation-history model, no auto-repair of incomplete legacy days,
single broker, no outbox archive/cleanup policy, and no public-deployment security.
No live OpenAI service call or manual browser visual review was performed. Streamlit
interactions were exercised through AppTest and APIs through the real isolated stack.

Final Git state: feature branch with 19 modified tracked files and 15 added files,
all uncommitted; nothing staged, committed, pushed or merged.
