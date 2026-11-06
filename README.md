# AI-Powered Smart Energy Management System

## Project Introduction

We are Group 25 from the Compact Programming course at FH Dortmund. Our project aims to monitor energy usage in buildings, analyse consumption and support energy-saving decisions. For Hometask 1, we implemented the Python classes for our three subsystems.

## Team Members

| Member | Student ID | Program | Subsystem | Python Classes |
|---|---|---|---|---|
| Rifat Ali Shaon | 7225871 | MDT | S1 — Energy Monitoring & Data Management | Building, Meter, EnergyReading, ReadingValidator, ReadingIngestionService, ConsumptionSummary, EnergyAnalyticsService |
| Syed Yasoob Raza | 7226703 | ESE | S2 — Sustainability & AI Coach | AIRecommendation, RecommendationFeedback, LLMRequestLog |
| Marwan Ahmed | 7226233 | MDT | S3 — Cost, Scenarios & Alerts | TariffPlan, CostCalculator, EnergyBudget, ScenarioSimulator, ScenarioResult, BaselineAnomalyDetector, AlertService, Notification |

## Hometask 1 Objective

Our assignment focuses on Object-Oriented Programming (OOP). We use classes to describe parts of our system and create objects to work with them. Constructors (`__init__`) set up each object, and attributes store its data. Getters read values, while setters update them and check inputs where needed.

Instance methods let our objects perform actions, such as adding a reading or acknowledging a notification. We practise encapsulation by providing methods to access and update data. We also show relationships between classes: a building contains meters, and each meter stores energy readings.

## S1 — Energy Monitoring & Data Management

We implemented seven classes for monitoring and summarising energy usage:

- `Building` stores building details and manages its meters, including a list of active meters.
- `Meter` stores its category, unit and active status. It holds energy readings and finds the latest one by timestamp.
- `EnergyReading` stores a timestamp, energy consumption, power, source and validity flag. Its `to_dict()` method prepares the data for serialization.
- `ReadingValidator` checks readings before ingestion. It requires an active meter, a valid reading, finite measurements, nonnegative consumption and a timezone-aware UTC timestamp.
- `ReadingIngestionService` validates and stores single readings, batches and event dictionaries. It checks a whole batch before storing anything, so a rejected batch leaves existing readings unchanged.
- `ConsumptionSummary` stores energy totals, category totals, peak power and the reading count for a time interval. It uses `Decimal` for energy values and serializes them as strings to preserve precision.
- `EnergyAnalyticsService` builds summaries from a building's meters. It separates load consumption from solar generation and calculates net grid energy as load minus solar. A negative result means export. It includes the start of the interval, excludes the end, and skips inactive meters and invalid readings. Peak power is the highest individual load-meter reading.

Our buildings contain meters, and our meters store readings. The services validate, ingest and summarise this data. Our current implementation stores data in memory.

## S2 — Sustainability & AI Coach

We implemented three classes for recommendations, feedback and request records:

- `AIRecommendation` stores an energy-saving recommendation, estimated savings in kWh, its source (`LLM` or `rules`), status (`NEW`, `ACCEPTED` or `DISMISSED`) and feedback. Methods allow us to accept or dismiss it.
- `RecommendationFeedback` stores a rating from 1 to 5 and an optional comment. It checks the rating and cleans up the comment.
- `LLMRequestLog` records the AI model name, execution time in milliseconds, success status and recording time. Its `record()` method updates the request record.

These classes store recommendation data. AI providers and forecasting services shown in the UML are planned Capstone work.

## S3 — Cost, Scenarios & Alerts

We implemented eight classes to support energy cost decisions:

- `TariffPlan` stores the electricity price per kWh and its start date.
- `CostCalculator` estimates electricity costs and projects monthly costs from daily consumption.
- `EnergyBudget` stores a monthly spending limit, tracks costs and checks whether a projection exceeds the limit.
- `ScenarioSimulator` estimates how percentage reductions in energy usage affect grid energy and monthly costs.
- `ScenarioResult` stores the simulated grid energy, monthly cost and savings, and provides `to_dict()` for serialization.
- `BaselineAnomalyDetector` compares energy readings with a baseline and identifies unusually high usage.
- `AlertService` checks budget overruns and anomalies, then creates notifications.
- `Notification` stores a message, severity and creation time, and lets us acknowledge it.

We have implemented and tested the three subsystems separately. Their interfaces are not yet fully connected.

## UML Class Diagrams

Our diagrams show the class structures and relationships. They also include planned Capstone classes and connections. The Python implementation for Hometask 1 includes only the seven S1, three S2 and eight S3 classes described above.

### S1 — Energy Monitoring & Data Management

![S1 UML Class Diagram](docs/uml/s1-hometask1.png)

### S2 — Sustainability & AI Coach

![S2 UML Class Diagram](docs/uml/s2-coach.png)

### S3 — Cost, Scenarios & Alerts

![S3 UML Class Diagram](docs/uml/s3-decisions.png)

## Project Structure

We keep each subsystem's code and tests in its own folder:

```text
.
├── backend/
│   ├── monitoring/
│   │   ├── domain/
│   │   ├── services/
│   │   └── tests/
│   ├── coach/
│   │   ├── domain/
│   │   └── tests/
│   └── decisions/
│       ├── domain/
│       ├── services/
│       └── tests/
├── docs/
│   └── uml/
└── README.md
```

## Running the Unit Tests

We use Python's built-in `unittest` framework. Run these commands from the project root.

**S1 — Energy Monitoring & Data Management**

```bash
python3 -m unittest discover -s backend/monitoring/tests -v
```

**S2 — Sustainability & AI Coach**

```bash
python3 -m unittest discover -s backend/coach/tests -v
```

**S3 — Cost, Scenarios & Alerts**

```bash
python3 -m unittest discover -s backend/decisions/tests -v
```

Our latest test run passed all 36 test methods:

| Subsystem | Test methods | Result |
|---|---:|---|
| S1 | 12 | Passed |
| S2 | 14 | Passed |
| S3 | 10 | Passed |

Our S1 tests use `subTest()` to check related valid inputs, invalid inputs and edge cases within the 12 methods.

## Video Presentation

**Video presentation:** [Watch our Hometask 1 presentation](https://drive.google.com/file/d/1xD4IJar7nnw1XJt82p9oObqoUe9krnT_/view?usp=sharing)

## Conclusion

We implemented 18 classes across our three subsystems. Through this assignment, we practised creating objects, checking inputs, using encapsulation and connecting related classes. Our unit tests help us check that these objects behave as expected.
