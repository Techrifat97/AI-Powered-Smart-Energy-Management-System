# AI-Powered Smart Energy Management System

**Hometask 3 — Web APIs & Database Access Layers**  
*Compact Programming Course (CPC) — Capstone Project (Group 25)*  
*Fachhochschule Dortmund (FH Dortmund)*

---

## Group Members (Group 25)

| Member | Student ID | Program | Subsystem |
| :--- | :---: | :---: | :--- |
| **Rifat Ali Shaon** | 7225871 | MDT | S1 — Energy Monitoring & Data Management |
| **Syed Yasoob Raza** | 7226703 | ESE | S2 — Sustainability & AI Coach |
| **Marwan Ahmed** | 7226233 | MDT | S3 — Cost, Scenarios & Alerts |

* **Repository:** [AI-Powered-Smart-Energy-Management-System](https://github.com/Techrifat97/AI-Powered-Smart-Energy-Management-System)
* **Video Demonstration:** [Assignment 3 API Demonstration Video](https://drive.google.com/file/d/1buvqB7mQ5Sy1reJsuSwuxF97OFEm9avi/view?usp=sharing)

---

## 1. System Architecture Overview

The system is built as a unified Python architecture:
* **Backend:** Django 5.2 + Django REST Framework (DRF), using **PostgreSQL for development, tests and deployment**.
* **AI Engine (S2):** OpenAI `gpt-4o-mini` with automated token tracking, latency auditing, and a built-in deterministic **Rule-Based Fallback** engine.
* **Frontend:** Streamlit is a planned dashboard; the current frontend folder is a placeholder.
* **Dependencies:** Unified single [`requirements.txt`](./requirements.txt) at the root level managing both Django and Streamlit packages.

```
CPC Project/
├── backend/
│   ├── manage.py                   # Django administration utility
│   ├── config/                     # Project settings, URLs, WSGI
│   │   ├── settings.py
│   │   └── urls.py
│   ├── monitoring/                 # S1: Buildings, Smart Meters, Telemetry
│   │   ├── models.py               # Building, Meter, EnergyReading
│   │   ├── serializers.py
│   │   ├── services/aggregation.py # Shared coverage, gross, solar & grid estimates
│   │   ├── services/ingestion.py   # Validated single-reading insertion
│   │   ├── services/generator.py   # Deterministic synthetic building-minutes
│   │   ├── views.py                # Aggregation & summary APIs
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── management/commands/
│   │       ├── seed_demo_data.py   # 14-day hourly demo data (1,008 new readings)
│   │       └── run_telemetry.py    # Synthetic completed-minute worker
│   ├── coach/                      # S2: Syed's Forecasting & AI Coach
│   │   ├── models.py               # ConsumptionForecast, AIRecommendation, LLMRequestLog
│   │   ├── serializers.py
│   │   ├── views.py                # Forecast & recommendation generation endpoints
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── services/
│   │       ├── forecaster.py       # 7-day diurnal load prediction & confidence bounds
│   │       ├── scorer.py           # Sustainability score (0-100), grade, carbon footprint
│   │       └── llm_coach.py        # OpenAI gpt-4o-mini integration & Rule-Based Fallback
│   ├── analysis/                   # S3: Marwan's Cost, Scenarios & Alerts
│   │   ├── models.py               # TariffPlan, EnergyAlert, CostReport
│   │   ├── serializers.py
│   │   ├── services/costs.py       # Explicit tariff estimates on S1 intervals
│   │   ├── views.py                # Tariff management, alerts, cost analysis APIs
│   │   ├── urls.py
│   │   └── admin.py
│   └── accounts/                   # Shared lightweight user authentication
├── frontend/                       # Streamlit application dashboard
├── .env.example                    # Template environment variables
├── .env                            # Local configuration (PostgreSQL & OpenAI key)
├── requirements.txt                # Unified Python requirements manifest
└── README.md
```

---

## 2. Quickstart & Installation

For the local Docker stack (PostgreSQL, one-shot migration, Gunicorn APIs and a
separate telemetry worker), use the [Docker development guide](docs/docker-development.md).
Docker has its own persistent database and private `.env.docker`; it does not
change the Postgres.app database or the local `.env`. The steps below remain the
host-based setup.

### Step 1: Create and Activate Virtual Environment
```powershell
# Create virtual environment
python -m venv .venv

# Activate on Windows PowerShell
.venv\Scripts\activate
```

On macOS or Linux, activate it with `source .venv/bin/activate`.

### Step 2: Install Unified Dependencies
```powershell
pip install -r requirements.txt
```

### Step 3: Set Up PostgreSQL

Install and start PostgreSQL 14 or newer, as supported by
[Django 5.2](https://docs.djangoproject.com/en/5.2/ref/databases/#postgresql-notes).
On macOS, Postgres.app is one option;
its command-line tools are in `/Applications/Postgres.app/Contents/Versions/latest/bin`.
On Windows or Linux, use your PostgreSQL installation's tools or package manager.

Open `psql -d postgres` as your local PostgreSQL administrator. Some installations
use `psql -U postgres -d postgres` instead. Create a development role and database:

```sql
CREATE ROLE smart_energy_user LOGIN CREATEDB;
\password smart_energy_user
CREATE DATABASE smart_energy_db OWNER smart_energy_user;
```

The `\password` command prompts for a password without putting it in SQL or shell
history. `CREATEDB` lets Django create a separate disposable database for tests;
the role does not need superuser permissions. A deployment role does not need
`CREATEDB` when tests are run separately.

The test role also needs permission to connect to the built-in `postgres`
database. See [Django's test database setup](https://docs.djangoproject.com/en/5.2/topics/testing/overview/#the-test-database).

### Step 4: Configure Environment Variables

Copy [`.env.example`](./.env.example) to `.env` in the project root. Set your own
`SECRET_KEY` and database password locally. Keep `.env` out of Git.

```env
# Django Settings
SECRET_KEY=replace-with-a-local-development-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,testserver

# PostgreSQL: set DB_PASSWORD in your local file before starting Django.
DB_NAME=smart_energy_db
DB_USER=smart_energy_user
DB_PASSWORD=
DB_HOST=127.0.0.1
DB_PORT=5432
DB_TEST_NAME=test_smart_energy_db

# OpenAI API Configuration (S2 Coach Subsystem)
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

The database engine is fixed to `django.db.backends.postgresql`. Missing connection
variables raise a configuration error; a stopped or unreachable server raises a
connection error. Django never switches to another database backend.

`DB_TEST_NAME` must start with `test_`, differ from `DB_NAME`, and fit PostgreSQL's
63-byte identifier limit. If omitted, it defaults to `test_` followed by `DB_NAME`.
Use a dedicated local PostgreSQL instance for tests, never a production server.
In deployment, supply the same environment variables through your hosting system;
credentials belong in local configuration or deployment secrets, not source files.

---

## 3. Database Migration & Telemetry Seeding

For a new development database, run the following commands to initialize it and
populate it with 14 days of realistic energy readings:

```powershell
# 1. Apply schema migrations
python backend/manage.py migrate

# 2. Populate a NEW demo database with explicit hourly telemetry (1,008 readings)
python backend/manage.py seed_demo_data

# 3. (Optional) Create superuser to inspect data in Django Admin UI
python backend/manage.py createsuperuser

# 4. Start the Django development server
python backend/manage.py runserver
```

For an existing database, inspect and back up its data before applying Phase 1's
`monitoring.0002_strengthen_s1_models` migration. Its initial check stops and reports
invalid numeric values, unsupported meter types/units, or duplicate
`(meter, timestamp)` readings. It does not delete or repair data automatically.
Valid hourly demo values and readings on deactivated meters are preserved;
hourly readings are not converted into 60-second measurements.

For continuous **synthetic** telemetry, use `python backend/manage.py run_telemetry`
or add `--once` for the latest completed UTC minute. This worker discovers current
inventory each cycle and saves through validated ingestion. It never backfills
downtime or creates assets. The simulator is our intended data source; manual
demos use the configured development database (`smart_energy_db`). See the
[generator guide](docs/simulated-telemetry.md); old unknown-duration data can block
ingestion and is never silently repaired.

S1 now supports building creation/updates, building-scoped meter setup, meter
activation/deactivation and paginated read-only history. See the
[dashboard API contract and manual verification steps](docs/s1-management-api.md).
Management permissions currently use `AllowAny`; these endpoints are for the
local development environment and are not ready for public internet deployment.

---

## 4. Implemented Web APIs (Hometask 3 Demonstration)

> 📹 **Demo Walkthrough Video:** [Watch the Assignment 3 Video Demonstration](https://drive.google.com/file/d/1buvqB7mQ5Sy1reJsuSwuxF97OFEm9avi/view?usp=sharing)

The following three endpoints demonstrate end-to-end data transfer between **Subsystem 1 (Monitoring)** and **Subsystem 2 (Forecasting & AI Coach)**:

```
[Smart Meters] ──> S1: GET /api/buildings/1/summary/ 
                        │
                        ▼
                   S2: GET /api/buildings/1/forecast/
                        │
                        ▼
                   S2: POST /api/recommendations/generate/
```

### Endpoint 1: S1 Monitoring Summary

`GET /api/buildings/{id}/summary/` summarizes all stored history, including
inactive meters. Only `ELECTRICITY` contributes to gross consumption and sampled
peak. HVAC and lighting are included submeters. Solar is separate generation.

For matching intervals with main 100, HVAC 40, lighting 20 and solar 30 kWh,
selected response fields are:

```json
{
  "total_consumption_kwh": 100.0,
  "peak_demand_kw": 20.0,
  "total_solar_generated_kwh": 30.0,
  "net_grid_consumption_kwh": 70.0,
  "estimated_grid_import_kwh": 70.0,
  "estimated_grid_export_kwh": 0.0,
  "main_data_available": true,
  "main_data_ambiguous": false,
  "grid_estimates_available": true
}
```

Here the main power sample is explicitly 20 kW. Recorded zero **energy** does not
imply zero power or zero balance: main 0 kWh, power 7 kW and solar 10 kWh gives
gross 0, peak 7, signed balance −10 and estimated export 10.

The shared functions in `backend/monitoring/services/aggregation.py` require
explicit interval durations for dependent results. Unknown/missing measurements
remain `null`, with availability reasons. Known nonoverlapping main replacements
are allowed; overlaps are flagged. Baseline is comparison information only.
`average_daily_kwh` includes partial recorded UTC days; `full_day_average_kwh`
uses only complete UTC days. Neither fills gaps with zeros.

`net_grid_consumption_kwh` retains its legacy name but is a **signed recorded
energy balance**, not imports. Separate import/export estimates require matching
main/solar intervals and assume no battery. Missing solar is not zero unless
`has_solar_installation=false` explicitly confirms absence for the reported history.

### Endpoint 2: S2 Energy Forecasting

`GET /api/buildings/{id}/forecast/` reuses S1 and requires at least two complete
UTC days in the preceding 14 completed calendar days. It returns seven heuristic
predictions starting tomorrow. Existing `confidence_*` fields are illustrative
bands, not calibrated 95% intervals. Insufficient data produces `forecast=[]`,
nullable prediction totals and `availability` explaining why; no baseline fallback.

### Endpoint 3: S2 AI Coach

`POST /api/recommendations/generate/` accepts:

```json
{"building_id": 1, "target_savings_pct": 15.0}
```

The response includes the all-history `energy_summary`, recent complete-day
`forecast_availability`, sustainability assessment and recommendations. Usable
generation retains HTTP 201. Insufficient or ambiguous data returns HTTP 200,
`availability.available=false`, empty recommendations and engine status `NOT_RUN`.
Daily assessment uses observed complete days, not extrapolated partial days.
Carbon uses matched-interval imports with an explicit scenario factor.
`estimated_daily_cost_eur` and new recommendation `estimated_savings_eur` are
`null`; S2 no longer applies a hardcoded electricity price. Weekly energy-saving
goals remain illustrative scenarios. No key selects the rule-based provider.

### Endpoint 4: S3 Cost Estimates

`GET /api/buildings/{id}/cost/` uses the same all-history interval report and
exactly one active global scenario tariff. Peak bands are UTC, including overnight
bands. Import charges and export compensation are separate; missing/ambiguous
pricing or unmatched measurements produce unavailable costs. An interval crossing
unequal price bands requires finer measurements.

Day export 10 kWh and night import 10 kWh retain both totals despite a zero signed
balance. At €0.30/kWh import and €0.08/kWh feed-in, the recorded-interval estimate
is €3.00 − €0.80 = €2.20. Gaps remain visible, and complete legacy cost totals stay
`null` if span coverage is incomplete. `complete_bill_available` is always false:
these estimates do not include contract history, fixed fees, taxes or a billing period.

See [shared measurement policy, API fields, limitations and teammate setup](docs/energy-calculations.md)
for the precise contract. New migrations preserve existing values and leave old
durations/solar status unknown. New demo data is hourly with explicit night solar
zeros; do not blindly label old rows or seed an existing database as a repair.

---

## 5. Automated Unit Tests

Tests use PostgreSQL and the normal project settings. Django creates
`DB_TEST_NAME`, applies migrations there, runs the tests, and drops that test
database afterwards. The application database is not used as the test database.
Never set `DB_TEST_NAME` to a database containing data you want to keep.

Run the configuration checks and the S1, S2 and S3 tests from the project root:

```powershell
python backend/manage.py check --database default
python backend/manage.py makemigrations --check --dry-run
python backend/manage.py test config monitoring coach analysis
git diff --check
```

For deterministic tests without external AI calls, leave `OPENAI_API_KEY` empty
in the test environment so S2 uses its rule-based provider. The S1 tests exercise
numeric constraints (including NaN and infinity), duplicate protection, history
retention after deactivation, and migration acceptance/rejection of legacy data.

If PostgreSQL is unavailable, start the server or correct the connection settings.
Do not substitute another database backend. Tests require permission to create
and drop their disposable database; migrations and tests must not be run against
the deployment database as a workaround.
