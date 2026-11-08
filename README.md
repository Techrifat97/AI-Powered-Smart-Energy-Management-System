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
* **Frontend:** Streamlit interactive dashboard communicating with backend REST endpoints.
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
│   │   ├── views.py                # Aggregation & summary APIs
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── management/commands/
│   │       └── seed_demo_data.py   # Realistic 14-day telemetry generator (812 readings)
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

# 2. Populate 14 days of realistic hourly telemetry (812 readings)
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
* **Route:** `GET /api/buildings/{id}/summary/`
* **Subsystem:** Subsystem 1 (Monitoring)
* **Purpose:** Aggregates meter readings for a building, computing total consumption, peak power demand, and solar PV generation.
* **Sample Response:**
```json
{
  "building_id": 1,
  "building_name": "Campus Science Complex - Block A",
  "area_sqm": 3500.0,
  "baseline_kwh_per_day": 320.0,
  "total_consumption_kwh": 9252.94,
  "average_daily_kwh": 660.92,
  "peak_demand_kw": 36.0,
  "total_solar_generated_kwh": 2142.28,
  "net_grid_consumption_kwh": 7110.66,
  "active_meters_count": 3,
  "total_readings_count": 812
}
```

---

### Endpoint 2: S2 Energy Forecasting
* **Route:** `GET /api/buildings/{id}/forecast/`
* **Subsystem:** Subsystem 2 (Forecasting)
* **Purpose:** Consumes S1 historical telemetry and generates a 7-day ahead forecast with weekday/weekend diurnal profiles, 95% confidence intervals, and trend detection.
* **Sample Response:**
```json
{
  "building_id": 1,
  "horizon_days": 7,
  "total_predicted_7d_kwh": 4605.82,
  "avg_daily_predicted_kwh": 657.97,
  "forecast": [
    {
      "forecast_date": "2026-11-06",
      "day_name": "Friday",
      "is_weekend": false,
      "predicted_kwh": 715.93,
      "confidence_lower_kwh": 658.66,
      "confidence_upper_kwh": 773.20,
      "trend": "INCREASING"
    },
    {
      "forecast_date": "2026-11-07",
      "day_name": "Saturday",
      "is_weekend": true,
      "predicted_kwh": 479.67,
      "confidence_lower_kwh": 436.50,
      "confidence_upper_kwh": 522.84,
      "trend": "INCREASING"
    }
  ]
}
```

---

### Endpoint 3: S2 AI Coach Actionable Recommendations
* **Route:** `POST /api/recommendations/generate/`
* **Subsystem:** Subsystem 2 (AI Coach)
* **Request Body:**
```json
{
  "building_id": 1,
  "target_savings_pct": 15.0
}
```
* **Workflow:**
  1. Retrieves S1 aggregated telemetry and S2 7-day forecasts.
  2. Computes the **Sustainability Assessment** (Score 0–100, Efficiency Grade A+–F, Carbon Footprint in $\text{kg CO}_2\text{e}$, daily cost in €).
  3. Prompts **OpenAI `gpt-4o-mini`** (or activates **Rule-Based Fallback** if no key is configured).
  4. Persists recommendations to `AIRecommendation` table and audits execution in `LLMRequestLog`.
* **Sample Response (HTTP 201 Created):**
```json
{
  "building": {
    "id": 1,
    "name": "Campus Science Complex - Block A",
    "baseline_kwh_per_day": 320.0
  },
  "sustainability_assessment": {
    "sustainability_score": 78.4,
    "efficiency_grade": "B",
    "daily_carbon_kg_co2": 195.54,
    "estimated_daily_cost_eur": 162.53,
    "solar_offset_ratio": 0.23
  },
  "forecast_preview": {
    "horizon_days": 7,
    "projected_weekly_total_kwh": 4605.82
  },
  "recommendations": [
    {
      "id": 1,
      "title": "Pre-Cooling & Peak Demand Shaving",
      "category": "PEAK_SHAVING",
      "priority": "HIGH",
      "suggested_action": "Peak demand reached 36.0 kW. Pre-cool high-occupancy zones between 06:30 and 08:30 to avoid 11:00-14:00 high-tariff spikes.",
      "estimated_savings_kwh": 270.0,
      "estimated_savings_eur": 86.40,
      "confidence_score": 0.92,
      "source": "OPENAI"
    }
  ],
  "engine_telemetry": {
    "source": "OPENAI",
    "status": "SUCCESS",
    "tokens_used": {
      "prompt_tokens": 412,
      "completion_tokens": 195,
      "total_tokens": 607
    },
    "latency_ms": 1150
  }
}
```

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
