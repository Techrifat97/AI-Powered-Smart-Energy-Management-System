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

---

## 1. System Architecture Overview

The system is built as a unified Python architecture:
* **Backend:** Django 5.2 + Django REST Framework (DRF) running against **PostgreSQL** (with offline SQLite support via toggle).
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

### Step 2: Install Unified Dependencies
```powershell
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables
Copy `.env.example` to `.env`:
```env
# Django Settings
SECRET_KEY=django-insecure-smart-energy-management-2026-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,testserver,*

# Database Configuration (PostgreSQL)
# Set USE_SQLITE=True for local offline development without a PostgreSQL server
USE_SQLITE=False
DB_ENGINE=django.db.backends.postgresql
DB_NAME=smart_energy_db
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=127.0.0.1
DB_PORT=5432

# OpenAI API Configuration (S2 Coach Subsystem)
OPENAI_API_KEY=sk-proj-your-api-key-here
OPENAI_MODEL=gpt-4o-mini
```

---

## 3. Database Migration & Telemetry Seeding

Run the following commands to initialize your database and populate it with 14 days of realistic energy readings:

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

---

## 4. Implemented Web APIs (Hometask 3 Demonstration)

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

To run the full suite of automated tests verifying S1 and S2 API endpoints:

```powershell
python backend/manage.py test monitoring coach analysis
```
```text
Creating test database for alias 'default'...
...
----------------------------------------------------------------------
Ran 3 tests in 0.047s

OK
Destroying test database for alias 'default'...
```
