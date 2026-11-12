# Docker: local development and university demonstration

Run Bash/zsh commands from the repository root with Docker Desktop running.
The stack supports Apple Silicon. Streamlit runs separately on the host.
PostgreSQL and Kafka ports remain internal; the API binds to localhost.

## First setup

Create private configuration **only if it does not already exist**:

```sh
python3 - <<'PY'
from pathlib import Path
import secrets
p = Path('.env.docker')
if p.exists():
    print('Existing private configuration retained.')
else:
    text = Path('.env.docker.example').read_text()
    text = text.replace('DOCKER_SECRET_KEY=\n', 'DOCKER_SECRET_KEY=' + secrets.token_urlsafe(48) + '\n')
    text = text.replace('DOCKER_DB_PASSWORD=\n', 'DOCKER_DB_PASSWORD=' + secrets.token_urlsafe(32) + '\n')
    p.write_text(text)
    p.chmod(0o600)
PY

dc() { docker compose --env-file .env.docker -p smart-energy "$@"; }
dc config --quiet
dc build backend
dc up -d
dc ps -a
```

Keep the existing `.env`, `.env.docker` and database password. PostgreSQL initialization
variables do not rotate credentials in an existing volume. Never share rendered
Compose configuration or unrestricted environment output: they can contain secrets.
The Dockerfile copies backend code and requirements, excluding private files.

## Services and startup

| Service | Role | Dependency |
| --- | --- | --- |
| `db` | PostgreSQL 18, persistent `postgres_data` | Healthy before migrations |
| `migrate` | Additive Django migrations, one shot | Healthy database |
| `demo_bootstrap` | Explicit demo-mode safe initialization, one shot | Successful migrations |
| `kafka` | Apache Kafka 4.3.2, single-node KRaft, persistent `kafka_data` | Broker health check |
| `kafka_init` | Idempotently create raw/dead-letter topics, one shot | Healthy broker |
| `backend` | Gunicorn JSON API, two workers | Successful bootstrap |
| `telemetry` | OOP producer, `run_telemetry --mode kafka` | Bootstrap and topics complete |
| `consumer` | `consume_telemetry`, validated atomic PostgreSQL writes | Bootstrap and topics complete |

All application services share the same built image. Rebuild with `dc build backend`
and run `dc up -d` after source changes. The default tag is `smart-energy-app:kafka-oop`,
configurable through `SMART_ENERGY_IMAGE`. No source reload is enabled.
One-shot jobs showing **Exited (0)** are successful. Workers restart on failure;
inspect repeated failures rather than assuming running means data is arriving.

The PostgreSQL mount remains `/var/lib/postgresql` with its existing
`smart-energy_postgres_data` volume. Kafka uses `smart-energy_kafka_data`.
Neither is shared with host Postgres.app. Do not delete/recreate existing volumes.
Backend health checks exercise the building API and database, not Kafka freshness.

```sh
dc logs --tail 30 migrate demo_bootstrap kafka_init
dc logs --tail 30 telemetry consumer
curl -fsS http://127.0.0.1:8000/api/buildings/
```

## Automatic synthetic history

`DEMO_MODE=true` is the Compose default. Set `DEMO_MODE=false` for a non-demo
installation: bootstrap then creates no buildings, meters, tariff or history.
The simulator itself remains synthetic in either mode; stop workers if no synthetic
live measurements are wanted.

A fresh demo receives four dedicated reserved-device meters (ELECTRICITY, HVAC,
LIGHTING, SOLAR), 14 previous complete UTC days with 3600-second intervals, matching
main/solar timestamps and night solar zeros. A flat EUR 0.30/kWh tariff with EUR
0.08/kWh export credit is created on first initialization if no active tariff exists.
Existing tariff records and rates are preserved. Later restarts do not reactivate
a tariff the user has deactivated; multiple active tariffs are reported without repair.

`DemoDataset.key=capstone-demo-v1` records stable identity. Before that marker exists,
the four reserved `DOCKER-DEMO-*` device IDs recognize renamed inventory. Names are
never reset. Repeated bootstrap leaves records unchanged, including user meter status,
forecasts and recommendations. Existing dedicated readings without a marker are
adopted **without backfill**. Conflicting device IDs/inventory are reported and skipped;
backend startup continues, while invalid telemetry inventory remains paused.

Normal Building Management never calls bootstrap. New user buildings have no history.
`setup_demo_inventory` remains an optional **inventory-only** command; the older
`seed_demo_data` is a historical manual fixture, not the startup path. Do not run it
against the current demo as a repair tool.

For a long-lived dedicated demo, explicitly refresh only completely empty recent days:

```sh
dc exec backend python backend/manage.py bootstrap_demo --refresh
```

This requires demo mode. It fills wholly empty days among the previous 14 UTC days,
never days containing any building reading or crossing/unknown coverage. Partial days
are reported and skipped, never repaired or overwritten. Existing user changes can
make inventory incompatible; review the error instead of resetting it. Refresh is
not scheduled, and cannot guarantee 14 usable days if partial live days already exist.

## Dashboard and demonstration

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r frontend/requirements.txt
streamlit run frontend/app.py
```

Open the printed Streamlit URL, normally http://localhost:8501. Its API default is
http://127.0.0.1:8000/api; override with `SMART_ENERGY_API` for a different port.
No key is required for rule-based recommendations. `OPENAI_API_KEY` is optional in
Compose; leave it unset for demonstrations that must not call external services.

1. Select the dedicated demo building and inspect Overview.
2. Open Forecast for seven daily heuristic values.
3. Generate Recommendations and expand Sustainability Assessment.
4. Open Costs; select previous complete UTC dates on Reports and Scenarios.
5. Open Building Management, create a building with explicit solar status.
6. Open Meter Management, add a main meter and activate it; add/activate solar if installed.
7. Wait for two UTC minute boundaries. A meter created at 12:00:30 first qualifies
   for 12:01–12:02. Inspect Kafka logs and the reading API.
8. Deactivate a submeter. Main telemetry continues; old readings remain. Deactivating
   a required main/solar pauses the building and requires UI confirmation.

## Verify Kafka and stored data

```sh
dc exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --describe --topic energy.readings.raw
dc exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka:9092 --topic energy.readings.raw --from-beginning --max-messages 1 --timeout-ms 10000
# Replace 1 with the demo building ID.
curl -fsS 'http://127.0.0.1:8000/api/buildings/1/readings/?page_size=8'
curl -fsS http://127.0.0.1:8000/api/buildings/1/summary/
```

Messages are versioned building-minute batches containing individual measurements.
Kafka ordering uses building ID keys; all meters in that building share a partition.
See [delivery and recovery](kafka.md), [OOP UML](s1-architecture.md) and [tests](testing.md).

## Select exactly one pipeline

Compose runs Kafka only. The old direct mode remains for explicit host/debug use.
Do **not** launch it alongside the Kafka workers. To temporarily use direct mode:

```sh
dc stop telemetry consumer
dc exec backend python backend/manage.py run_telemetry --mode direct
# Ctrl+C the direct command before resuming Kafka:
dc up -d telemetry consumer
```

Pending older Kafka batches may then conflict with direct-mode history and go to the
DLQ. Avoid mode changes during normal demonstrations; they are not a repair workflow.

## Restart and persistence

```sh
dc stop
dc up -d
dc down             # Retains both named volumes; NEVER add -v.
dc up -d
```

Do not flush the database or replace volumes. Restart resumes unprocessed outbox
batches and committed Kafka offsets; duplicate deliveries are safe. Downtime gaps
are not automatically filled. A single Kafka node is a university demo, not a
high-availability cluster. There is no authentication, TLS or public deployment
hardening; do not publish this stack to the internet.
