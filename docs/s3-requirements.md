# S3 requirements: costs, scenarios, alerts and reports

Subsystem 3 turns the S1 measurements into money, savings ideas and warnings.
Each requirement names where it is implemented and how it is checked.
Tests: `backend/analysis/tests.py`, `test_scenario_periods.py`, `test_explainer.py`
and `frontend/test_app.py`. Results: [test-results/s3-test-results.md](test-results/s3-test-results.md).

## Functional requirements

| ID | Requirement | Implemented in | Verified by |
| --- | --- | --- | --- |
| FR-1 | A user can enter the electricity price (standard rate, optional peak rate and hours, solar feed-in credit). Exactly one price plan is active; saving a new one switches the old one off automatically. | `TariffPlan`, `TariffPlanSerializer`, Costs page | `TariffValidationTests`, `test_changing_price_switches_off_old_tariff` |
| FR-2 | The system estimates a building's electricity cost from recorded intervals: grid purchases, solar feed-in credit and net cost. | `services/costs.py` (`cost_analysis`) | `AnalysisAPITests`, `ReportAndScenarioTests` |
| FR-3 | The Costs page shows the total, the average per day and a "where the money goes" breakdown in plain language. | `frontend/app.py` (`costs`) | `test_costs_page_shows_total_and_breakdown` |
| FR-4 | A user can ask "what if" with less electricity, more solar power or a different price, and sees the saving in EUR compared with today. | `services/scenarios.py` (`run_scenario`), What if page | `test_scenario_consumption_reduction_lowers_cost`, `test_more_solar_idea_sends_solar_change` |
| FR-5 | Without chosen dates, a scenario uses the latest unbroken run of fully recorded days; the user can also choose dates. | `latest_complete_period` | `test_complete_history_still_works_after_live_gap`, `test_scenario_custom_dates_are_sent` |
| FR-6 | The system detects four kinds of problems: peak spike, unusual night load, meter offline and daily budget exceeded. | `services/alerts.py` (`AlertRule` subclasses, `AlertDetector`) | `AlertDetectionTests` |
| FR-7 | An open alert of the same type for the same building and meter is not created twice. | `AlertDetector.detect` | `AlertDetectionTests` |
| FR-8 | A user can list alerts, filter open ones and mark an alert as resolved; each alert explains what it means. | Alerts API and page | `test_alerts_page_explains_and_resolves` |
| FR-9 | A user can store a cost report for fully recorded days, list stored reports and download them as CSV. | `services/reports.py`, Reports page | `test_report_*` in `ReportAndScenarioTests` |
| FR-10 | A user can get a plain-language explanation of the costs with saving tips, written by OpenAI when configured and by built-in rules otherwise. | `services/explainer.py`, `POST /cost/explain/` | `test_explainer.py`, `test_explain_my_costs_shows_text_and_source` |

## Non-functional requirements

| ID | Requirement | How it is met |
| --- | --- | --- |
| NFR-1 Usability | A person without technical knowledge can use every S3 page: plain sentences, help texts, no raw error codes. | Every page has an intro and help; API reason codes are translated by `explain()`; glossary in the sidebar. |
| NFR-2 Correctness of money | Money is calculated with `Decimal` and rounded half-up to cents; the same interval is never priced twice. | `costs.py`, `scenarios.py`; checked against hand-calculated values in `ReportAndScenarioTests`. |
| NFR-3 Honesty about data | No value is invented: missing or incomplete data gives a clear "not available" reason instead of zero. | `reason` codes in all responses; `test_missing_main_or_solar_not_zero_filled`. |
| NFR-4 Availability of AI feature | The explanation always answers, even without an API key, without network or when OpenAI fails. | `explain_costs` falls back to `RuleBasedCostExplainer`; `test_falls_back_to_rules_when_openai_fails`. |
| NFR-5 Security | All S3 endpoints require a JWT login; the OpenAI key is read from the environment and never stored or logged. | `IsAuthenticated` on all views; `test_api_requires_login`. |
| NFR-6 Validation | Invalid input (negative prices, equal peak hours, start after end, percentages out of range) is rejected with HTTP 400. | Serializers; `test_scenario_validation`, `TariffValidationTests`, `test_bad_dates_and_percentages`. |
| NFR-7 Performance | A cost, scenario or explanation request answers within a few seconds for 14 days of data; the OpenAI call times out after 12 s. | Single pass over intervals; OpenAI `timeout=12`, no retries; dashboard daily totals cached for 5 minutes. |
| NFR-8 Maintainability | New alert rules or explainers are added as one new subclass, without changing the detector or the API. | Abstract `AlertRule` and `CostExplainer`; see the UML diagram. |
| NFR-9 Testability | All S3 logic is covered by automated tests that run without network access; OpenAI is replaced by a fake client. | 41 backend tests and the dashboard tests; `OPENAI_API_KEY=` during tests. |
| NFR-10 Portability | S3 runs in the team's Docker setup with one command (`docker compose up`), with PostgreSQL. | `Dockerfile`, `compose.yaml`; [Docker development](docker-development.md). |
