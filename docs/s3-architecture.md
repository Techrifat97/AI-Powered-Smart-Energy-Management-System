# S3 architecture: costs, scenarios, alerts and reports

Subsystem 3 (owner: Marwan Ahmed) lives in `backend/analysis/` and is shown in the
dashboard pages **Costs**, **Scenarios** ("What if...?"), **Reports** (sidebar group
*Money*) and **Alerts** (group *Monitor*). It reads the shared S1 measurements and
never changes them.

- UML class diagram: [uml/s3-analysis.mmd](uml/s3-analysis.mmd) (Mermaid)
- Requirements: [s3-requirements.md](s3-requirements.md)
- Test results: [test-results/s3-test-results.md](test-results/s3-test-results.md)

## What S3 does for the user

| Page | Question it answers |
| --- | --- |
| Costs | "What did my electricity cost, and where does the money go?" Includes an **Explain my costs** button (OpenAI). |
| What if...? | "How much would I save if I used less, had more solar or switched tariff?" |
| Alerts | "Is anything wrong right now, and what should I do?" |
| Reports | "Save and download the cost of a fixed period." |

## Classes and responsibilities

| Class | Role |
| --- | --- |
| `AlertRule` (abstract) | Interface for one detection rule; subclasses implement `evaluate()` and return a `Finding` or `None`. |
| `PowerSeriesRule` (abstract) | Shared base for rules that analyse 24 h of meter power, loaded into a Pandas `Series`. |
| `PeakSpikeRule`, `NightLoadRule` | Electricity rules using NumPy means and Pandas time filtering. |
| `MeterOfflineRule`, `DailyBudgetRule` | Direct `AlertRule` subclasses (per meter and per building). |
| `Finding` | Frozen dataclass: severity, message, observed value and threshold. |
| `AlertDetector` | Holds a list of rules (composition), runs them polymorphically and stores non-duplicate `EnergyAlert` rows. |
| `CostExplainer` (abstract) | Interface for turning cost facts into a plain-language text. |
| `OpenAICostExplainer` | Calls the OpenAI chat API (`OPENAI_MODEL`, default `gpt-4o-mini`) when `OPENAI_API_KEY` is set. |
| `RuleBasedCostExplainer` | Template text from the same facts; works offline and is the fallback. |
| `TariffPlan`, `EnergyAlert`, `CostReport` | Django models (database access layer). |
| `AnalysisError` -> `ReportUnavailable`, `ExplanationUnavailable` | Exception hierarchy. `reason` codes are translated into plain sentences in the dashboard. |

## OOP and course topics shown

- **Abstract classes**: `AlertRule`, `PowerSeriesRule`, `CostExplainer`.
- **Inheritance**: two levels (`AlertRule` -> `PowerSeriesRule` -> `PeakSpikeRule`).
- **Polymorphism**: `AlertDetector` calls `evaluate()` and `explain_costs()` calls `explain()` without knowing the concrete class.
- **Composition / aggregation**: a detector is composed of rules; the explanation service tries a list of explainers; alerts and reports reference buildings, meters and tariffs.
- **NumPy and Pandas**: alert rules; daily charts in the dashboard.
- **Exception handling**: custom hierarchy, serializer validation, `ReportUnavailable` -> HTTP 422, OpenAI failures -> fallback.
- **Web API and database**: Django REST Framework endpoints over PostgreSQL.
- **OpenAI API**: cost explanation with a safe fallback.
- **Unit tests**: 41 backend tests and the dashboard tests (see test results).

## How the main features work

**Costs.** Every recorded interval is priced with the single active tariff
(standard or peak rate). Electricity used minus solar generated is bought from the
grid; surplus solar earns the feed-in credit. Money is calculated with `Decimal`. No
battery is assumed; results are estimates, not invoices. Saving a new price in the
dashboard creates it inactive, switches off the old tariff and then activates the new
one, because only one tariff may be active.

**What if...?** `run_scenario()` re-prices the same intervals with a consumption
change, a solar change or another price, and returns the difference. Without dates it
uses the **latest unbroken run of fully recorded days** (`latest_complete_period()`),
because live telemetry leaves today incomplete and restarts leave gaps. The
alternative tariff keeps the active tariff's peak hours and feed-in, so only the
values the user changes differ.

**Explain my costs.** `build_cost_facts()` collects the cost figures and the saving of
a 10 % reduction. `explain_costs()` tries `OpenAICostExplainer` first (only when a key
is configured) and falls back to `RuleBasedCostExplainer` on any error, so the button
always answers. The dashboard shows who wrote the text.

**Alerts.** `AlertDetector` runs four rules: peak spike (latest power > 2x the 24 h
average), unusual night load (00:00-05:00 UTC mean > 50 % of daytime), meter offline
(no data for 15 min) and daily budget (yesterday above the building's baseline). An
open alert of the same type is never duplicated.

**Reports.** A report stores the cost of fully recorded UTC days; otherwise
`ReportUnavailable` explains why (HTTP 422).

## API

| Endpoint | Purpose |
| --- | --- |
| `GET/POST /api/tariffs/`, `GET/PATCH /api/tariffs/{id}/` | Manage tariffs (one active) |
| `GET /api/buildings/{id}/cost/` | Cost estimate |
| `POST /api/buildings/{id}/cost/explain/` | Plain-language cost explanation (OpenAI or rules) |
| `POST /api/buildings/{id}/scenarios/` | What-if scenario |
| `GET/POST /api/buildings/{id}/reports/`, `GET /api/reports/` | Cost reports |
| `GET /api/alerts/`, `POST /api/alerts/detect/`, `PATCH /api/alerts/{id}/` | Alerts |

All endpoints require a JWT login. Details: [S2/S3 APIs](coach-analysis-api.md).
