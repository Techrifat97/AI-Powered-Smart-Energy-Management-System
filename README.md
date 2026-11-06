# AI-Powered Smart Energy Management System

**Hometask 3 — Web APIs & Database Access Layers**

## Student Identification
* **Student Name:** Syed Yasoob Raza
* **Student ID:** 7226703
* **Program:** Embedded Systems Engineering (ESE)
* **Course:** Compact Programming Course — Capstone Project
* **Group:** Group 25
* **Repository:** [AI-Powered-Smart-Energy-Management-System](https://github.com/Techrifat97/AI-Powered-Smart-Energy-Management-System)

---

## 1. Project Overview & Architecture

This repository contains the foundational **Django 5.2 + Django REST Framework (DRF)** backend architecture configured for **PostgreSQL**.

The backend structure has been cleanly reset as an empty baseline ready for domain implementation:
* **`config/`**: Central project configuration, settings, database connections, and URL dispatching.
* **`monitoring/`**: Subsystem 1 app (Energy Monitoring & Data Management).
* **`coach/`**: Subsystem 2 app (Sustainability & AI Coach).
* **`accounts/`**: Subsystem 3 app (User Management & Alerts).

### Clean Baseline Directory Layout
```
F:\CPC Project\
├── backend\
│   ├── manage.py           # Django administrative utility
│   ├── requirements.txt    # Project dependencies
│   ├── config\             # Project settings, WSGI/ASGI, URLs
│   │   ├── asgi.py
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── wsgi.py
│   │   └── __init__.py
│   ├── monitoring\         # Clean app ready for models, serializers, views
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── tests.py
│   │   ├── views.py
│   │   ├── __init__.py
│   │   └── migrations\
│   │       └── __init__.py
│   ├── coach\              # Clean app ready for models, serializers, views
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── tests.py
│   │   ├── views.py
│   │   ├── __init__.py
│   │   └── migrations\
│   │       └── __init__.py
│   └── accounts\           # Clean app ready for models, serializers, views
│       ├── admin.py
│       ├── apps.py
│       ├── models.py
│       ├── tests.py
│       ├── views.py
│       ├── __init__.py
│       └── migrations\
│           └── __init__.py
├── .env.example            # Sample environment variables
├── .env                    # Local configuration
├── requirements.txt        # Root requirements
└── README.md
```

---

## 2. Requirements & Installation

### Dependencies Installed
* `Django>=5.0,<6.0`
* `djangorestframework>=3.15.0`
* `django-cors-headers>=4.3.0`
* `python-dotenv>=1.0.0`
* `psycopg2-binary>=2.9.9`

### Installation
```bash
pip install -r requirements.txt
```

---

## 3. Database Configuration (PostgreSQL)

Configure your local database credentials in `.env`:
```env
USE_SQLITE=False
DB_ENGINE=django.db.backends.postgresql
DB_NAME=smart_energy_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=127.0.0.1
DB_PORT=5432
```

*(Set `USE_SQLITE=True` if PostgreSQL is not currently running locally)*

---

## 4. System Verification

Verify that Django loads with zero configuration issues:
```bash
python backend/manage.py check
```
*(Result: `System check identified no issues (0 silenced).`)*
