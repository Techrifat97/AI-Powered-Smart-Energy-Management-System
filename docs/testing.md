# Testing and verification

All tests use PostgreSQL and the normal project settings. Django creates the
selected test database, applies migrations **there**, runs tests and drops it.
`DB_TEST_NAME` must start with `test_`, differ from the application database name
and fit PostgreSQL's identifier limit. It must name disposable data only. Do not
reuse a database belonging to another running test session.

Commands below use Bash/zsh from the repository root. No external AI calls are
needed: pass `--env OPENAI_API_KEY=` to one-off Compose tests; AI-dependent tests use mocks or the
rule-based provider. Test execution does not establish live OpenAI reliability.

## Docker image tests

Define `dc` as in [Docker setup](docker-development.md#first-setup). With the
database and backend already running:

```sh
dc exec backend python backend/manage.py check --database default
dc exec backend python backend/manage.py makemigrations --check --dry-run
dc exec -e OPENAI_API_KEY= backend python backend/manage.py test config monitoring coach analysis --noinput
git diff --check
```

The default Docker test database is `test_smart_energy_docker`. The development
role can create/drop it. `--noinput` assumes this database is disposable and can
be removed if left by a failed session. Tests must never target the running
application database. The continuous worker can remain running: its application
database is separate from the test database.

These commands exercise code **already built into the backend image**. Source
edits are not automatically copied into a running container.

## Working-tree tests without restarting services

An existing image can supply dependencies while a one-off container reads the
current backend source through a read-only bind mount:

```sh
dc run --rm --no-deps -T \
  --volume "$PWD/backend:/app/backend:ro" \
  --env OPENAI_API_KEY= \
  backend python backend/manage.py test config monitoring coach analysis --noinput
```

No image is rebuilt and no existing service is restarted. `--no-deps` requires the
Docker database/network to be running already. The one-off container does not
publish the backend port. The same read-only mount can be used with the `check`
and migration-consistency commands above. This tests the mounted working-tree
code with the existing image's dependency versions; dependency changes require
an updated image in a normal development workflow.

## Host tests

Use the virtual environment and connection configuration described in
[host development](host-development.md#environment). The role needs database
creation permission and access to the PostgreSQL maintenance database.

```sh
OPENAI_API_KEY='' python backend/manage.py check --database default
OPENAI_API_KEY='' python backend/manage.py makemigrations --check --dry-run
OPENAI_API_KEY='' python backend/manage.py test config monitoring coach analysis --noinput
git diff --check
```

For PowerShell, set `$env:OPENAI_API_KEY = 'disabled-for-tests'` before the Python
commands rather than using the Bash assignment prefix. This non-key placeholder
fails the provider's key check and prevents a private file from supplying a real
key. Private `.env` files are not
modified for test execution. If PostgreSQL or permissions are unavailable, report
the blocker; do not substitute SQLite or use the application database for tests.

## Coverage and limits

The suite exercises model validation/database constraints, duplicate handling,
shared energy calculations, management/history APIs, selected PostgreSQL
concurrency cases, completed-minute scheduling, per-building rollback, legacy
migration preservation/rejection, demo initialization and graceful shutdown.
Timing-sensitive tests use controlled clocks rather than minute-long waits.

Passing tests do not demonstrate calibrated forecast accuracy, measured savings,
realistic weather/building behavior, performance under load or secure public
access. Dashboard interactions have separate Streamlit AppTest tests; UML and
presentation appearance are not covered by the backend tests. Migration tests operate on disposable schemas; they are not
an audit or repair of the running application's legacy data.


## New S1 and dashboard coverage

`monitoring.test_bootstrap_profiles` checks ABCs, strategies, immutable energy
addition, deterministic streaming, complete demo days, repeat/renamed bootstrap,
refresh preservation and real S2/S3 availability with OpenAI disabled.
`monitoring.test_kafka_pipeline` uses PostgreSQL with mocked broker I/O to check
strict schemas, acknowledgment failures, atomic inserts, conflicting/partial
batches, inventory changes, DLQ/offset policy and two concurrent consumers.
`analysis.test_scenario_periods` checks paired inclusive dates, gaps, solar alignment,
legacy no-date behavior and identical baseline/scenario time scopes.

Run Streamlit interaction tests using the same built image and a read-only mount:

```sh
dc run --rm --no-deps -T --volume "$PWD/frontend:/app/frontend:ro" \
  --env OPENAI_API_KEY= backend python -m unittest discover -s frontend -p 'test_*.py'
```

## Fresh real-broker acceptance

Use a **new project name/volumes and port**, never your working demo database.
The acceptance script creates labeled inventory, forecasts, recommendations and a
report in this isolated environment, deletes nothing, and waits for real Kafka
minute cycles (up to about six minutes). It requires Python 3 standard library only.

```sh
OPENAI_API_KEY= DOCKER_BACKEND_PORT=18000 docker compose --env-file .env.docker \
  -p smart-energy-acceptance up -d --build
python3 scripts/verify_demo.py --isolated-api http://127.0.0.1:18000/api
# Verify normal stop/start preserves records and bootstrap remains idempotent:
DOCKER_BACKEND_PORT=18000 docker compose --env-file .env.docker -p smart-energy-acceptance stop
OPENAI_API_KEY= DOCKER_BACKEND_PORT=18000 docker compose --env-file .env.docker -p smart-energy-acceptance up -d
DOCKER_BACKEND_PORT=18000 docker compose --env-file .env.docker -p smart-energy-acceptance ps -a
# Release containers/network afterward, retaining data volumes:
DOCKER_BACKEND_PORT=18000 docker compose --env-file .env.docker -p smart-energy-acceptance down
```

The script deliberately accepts only localhost port 18000; ensure it belongs to the
isolated stack. Do not repoint it to an active demonstration database. A later run
on the same acceptance project preserves history and creates another labeled test
building; it is not a clean first-run check unless the project was initially fresh.
Broker-failure tests in the automated suite are mocked; normal broker startup,
transport and restart are also exercised by the real acceptance workflow.
