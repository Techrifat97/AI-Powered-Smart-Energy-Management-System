# AI-Powered Smart Energy Management System

AI-driven energy monitoring, analysis and sustainability coaching for buildings. Capstone Project, Home Assignment 1 (Object-Oriented Concepts).

## Team Overview

| Member | Subsystem | Django app | Implemented classes |
|---|---|---|---|
| Rifat Ali Shaon | S1 Monitoring & Analytics | `backend/monitoring` | Building, Meter, EnergyReading |
| Syed Yasoob Raza | S2 Forecasting & AI Coach | `backend/coach` | TODO |
| Marwan Ahmed | S3 Cost, Scenarios & Alerts | `backend/decisions` | TariffPlan, EnergyBudget, Notification, ScenarioResult, CostCalculator, ScenarioSimulator, BaselineAnomalyDetector, AlertService |

## System Design

UML class diagrams per subsystem (images in `docs/uml/`).

### S1 Monitoring & Analytics
![S1 class diagram](docs/uml/s1-monitoring.png)

### S2 Forecasting & AI Coach
![S2 class diagram](docs/uml/s2-coach.png)

### S3 Cost, Scenarios & Alerts
![S3 class diagram](docs/uml/s3-decisions.png)

## Presentation Link

[Team video presentation](TODO-paste-video-url-here)

## Project Structure

```
backend/<app>/domain/    entity classes (OOP)
backend/<app>/services/  service classes
backend/<app>/tests/     unit tests
docs/uml/                UML diagrams
frontend/                React app
```

## Running the tests

```
python -m unittest discover -s backend/decisions/tests -t .
```
