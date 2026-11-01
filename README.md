# AI-Powered Smart Energy Management System

AI-driven energy monitoring, analysis and sustainability coaching for buildings. Capstone Project, Home Assignment 1 (Object-Oriented Concepts).

## Team Overview

| Member | Subsystem | Django app | Implemented classes |
|---|---|---|---|
| Shaon | S1 Energy Monitoring & Analysis | `backend/monitoring` | Building, Meter, EnergyReading |
| Yassoub | S2 Sustainability & AI Coach | `backend/coach` | AIRecommendation, RecommendationFeedback, LLMRequestLog |
| Marwan | S3 Web Dashboard & Alerts | `backend/accounts` | User, UserPreferences, Notification |

## System Design

UML class diagrams per subsystem (images in `docs/uml/`).

### S1 Energy Monitoring
![S1 class diagram](docs/uml/s1-monitoring.png)

### S2 Sustainability & AI Coach
![S2 class diagram](docs/uml/s2-coach.png)

### S3 Web Dashboard & Alerts
![S3 class diagram](docs/uml/s3-accounts.png)

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
python -m unittest discover -s backend/accounts/tests -t .
python -m unittest discover -s backend/coach/tests -t .
```
