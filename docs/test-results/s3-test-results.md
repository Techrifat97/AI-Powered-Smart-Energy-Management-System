# S3 test results

Run on 2026-11-13 on branch `feature/s3-oop-ux-openai` (code as of commit `8e6107e`).

| Suite | Command | Result |
| --- | --- | --- |
| S3 backend (Django, PostgreSQL in Docker) | `docker compose ... run --rm backend python backend/manage.py test analysis` | **41 of 41 passed** |
| Dashboard (Streamlit `AppTest`, API mocked) | `python -m unittest discover -s frontend -p "test_*.py"` | **22 of 22 passed** |

OpenAI is never called during tests: `OPENAI_API_KEY` is empty and the OpenAI client is
replaced by a fake. The log line `Cost explanation fell back: openai_failed: network down`
is expected; it comes from the test that checks the fallback.

The dashboard suite covers the whole dashboard (S1, S2 and S3 pages). The S3 ones are
about costs, scenarios, alerts and the cost explanation.

## S3 backend tests

| Test class | Test | Result |
| --- | --- | --- |
| `ExplainCostsTests` | `test_api_endpoint_works_without_a_key` | passed |
| `ExplainCostsTests` | `test_api_requires_login` | passed |
| `ExplainCostsTests` | `test_falls_back_to_rules_when_openai_fails` | passed |
| `ExplainCostsTests` | `test_uses_openai_when_it_answers` | passed |
| `ScenarioPeriodTests` | `test_bad_dates_and_percentages` | passed |
| `ScenarioPeriodTests` | `test_complete_history_still_works_after_live_gap` | passed |
| `ScenarioPeriodTests` | `test_missing_main_or_solar_not_zero_filled` | passed |
| `ScenarioPeriodTests` | `test_missing_solar_alignment_rejected` | passed |
| `ScenarioPeriodTests` | `test_period_outside_data_rejected` | passed |
| `ScenarioPeriodTests` | `test_same_period_used_for_modified_price` | passed |
| `AlertDetectionTests` | `test_alert_update_only_changes_resolution_and_list_filters` | passed |
| `AlertDetectionTests` | `test_budget_exceeded_uses_complete_days_only` | passed |
| `AlertDetectionTests` | `test_detect_endpoint_and_validation` | passed |
| `AlertDetectionTests` | `test_meter_offline_and_duplicates_are_not_repeated` | passed |
| `AlertDetectionTests` | `test_no_alert_for_steady_load` | passed |
| `AlertDetectionTests` | `test_peak_spike` | passed |
| `AlertDetectionTests` | `test_unusual_night_load` | passed |
| `AnalysisAPITests` | `test_cost_analysis_endpoint` | passed |
| `AnalysisAPITests` | `test_tariff_list` | passed |
| `ReportAndScenarioTests` | `test_report_is_generated_and_listed` | passed |
| `ReportAndScenarioTests` | `test_report_is_refused_without_tariff_or_full_coverage` | passed |
| `ReportAndScenarioTests` | `test_report_rejects_bad_dates` | passed |
| `ReportAndScenarioTests` | `test_scenario_alternative_tariff_is_not_stored` | passed |
| `ReportAndScenarioTests` | `test_scenario_consumption_reduction_lowers_cost` | passed |
| `ReportAndScenarioTests` | `test_scenario_requires_active_tariff` | passed |
| `ReportAndScenarioTests` | `test_scenario_validation` | passed |
| `ReportAndScenarioTests` | `test_scenario_without_changes_equals_baseline` | passed |
| `TariffValidationTests` | `test_invalid_values_are_rejected` | passed |
| `TariffValidationTests` | `test_patch_keeps_active_tariff_valid` | passed |
| `TariffValidationTests` | `test_second_active_tariff_is_rejected_until_first_is_deactivated` | passed |
| `TariffValidationTests` | `test_valid_tariff_is_created` | passed |
| `ExplainerClassTests` | `test_cost_explainer_is_abstract` | passed |
| `ExplainerClassTests` | `test_empty_openai_answer_is_rejected` | passed |
| `ExplainerClassTests` | `test_openai_explainer_sends_facts_and_returns_text` | passed |
| `ExplainerClassTests` | `test_openai_failure_becomes_explanation_unavailable` | passed |
| `ExplainerClassTests` | `test_openai_is_only_used_with_a_real_looking_key` | passed |
| `ExplainerClassTests` | `test_rule_based_text_uses_the_real_numbers` | passed |
| `AlertRuleDesignTests` | `test_alert_rule_is_abstract` | passed |
| `AlertRuleDesignTests` | `test_default_rules_are_polymorphic_alert_rules` | passed |
| `AlertRuleDesignTests` | `test_detector_accepts_custom_rule_set` | passed |
| `AlertRuleDesignTests` | `test_report_unavailable_is_an_analysis_error` | passed |

## Dashboard tests

| Test class | Test | Result |
| --- | --- | --- |
| `DashboardTests` | `test_activate_meter` | passed |
| `DashboardTests` | `test_add_meter_and_surface_api_validation` | passed |
| `DashboardTests` | `test_alerts_page_explains_and_resolves` | passed |
| `DashboardTests` | `test_blank_name_rejected_before_request` | passed |
| `DashboardTests` | `test_changing_price_switches_off_old_tariff` | passed |
| `DashboardTests` | `test_cheaper_tariff_keeps_active_hours_and_feed_in` | passed |
| `DashboardTests` | `test_costs_page_guides_user_without_tariff` | passed |
| `DashboardTests` | `test_costs_page_shows_total_and_breakdown` | passed |
| `DashboardTests` | `test_create_first_building_without_inventory` | passed |
| `DashboardTests` | `test_duplicate_names_have_distinct_labels` | passed |
| `DashboardTests` | `test_explain_my_costs_shows_text_and_source` | passed |
| `DashboardTests` | `test_more_solar_idea_sends_solar_change` | passed |
| `DashboardTests` | `test_required_deactivation_confirmation_and_history_warning` | passed |
| `DashboardTests` | `test_scenario_custom_dates_are_sent` | passed |
| `DashboardTests` | `test_scenario_result_is_explained_in_plain_words` | passed |
| `DashboardTests` | `test_scenario_runs_immediately_with_simple_default` | passed |
| `DashboardTests` | `test_scenario_without_tariff_explains_next_step` | passed |
| `DashboardTests` | `test_session_restored_from_query_params_on_page_reload` | passed |
| `DashboardTests` | `test_session_restored_on_tab_reload_even_without_query_params` | passed |
| `DashboardTests` | `test_team_management_deletes_member_with_confirmation` | passed |
| `DashboardTests` | `test_team_management_lists_members_and_adds_member` | passed |
| `DashboardTests` | `test_unauthenticated_session_shows_login_screen` | passed |
