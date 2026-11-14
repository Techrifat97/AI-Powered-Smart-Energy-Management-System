"""Cost explanations: OpenAI path (mocked), rule-based fallback and the API endpoint."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from analysis.services.errors import AnalysisError, ExplanationUnavailable
from analysis.services.explainer import (CostExplainer, OpenAICostExplainer, RuleBasedCostExplainer,
                                         default_explainers, explain_costs)
from monitoring.models import Building
from monitoring.services.demo import bootstrap_demo

FACTS = {
    'building_name': 'Campus Sonnenstraße Dortmund', 'location': 'Dortmund', 'tariff_name': 'Flat',
    'price_eur_per_kwh': 0.3, 'days_measured': 14.0, 'net_cost_eur': 492.65, 'cost_per_day_eur': 35.19,
    'grid_import_kwh': 1643.8, 'grid_import_cost_eur': 493.15, 'solar_generated_kwh': 840.0,
    'solar_export_kwh': 6.2, 'solar_export_credit_eur': 0.49, 'baseline_kwh_per_day': 900.0,
    'saving_if_10pct_less_eur': 72.34, 'saving_period_days': 14,
}


def fake_client(text=None, error=None):
    create = Mock(side_effect=error) if error else Mock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]))
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), create


class ExplainerClassTests(SimpleTestCase):
    def test_cost_explainer_is_abstract(self):
        with self.assertRaises(TypeError):
            CostExplainer()

    def test_rule_based_text_uses_the_real_numbers(self):
        text = RuleBasedCostExplainer().explain(FACTS)
        for figure in ('492.65 EUR', '35.19 EUR', '1,644 kWh', '72.34 EUR', '14 days'):
            self.assertIn(figure, text)

    def test_openai_explainer_sends_facts_and_returns_text(self):
        client, create = fake_client('You paid about 492.65 EUR.')
        explainer = OpenAICostExplainer('sk-test', 'gpt-4o-mini', client=client)
        self.assertEqual(explainer.explain(FACTS), 'You paid about 492.65 EUR.')
        sent = create.call_args.kwargs
        self.assertEqual(sent['model'], 'gpt-4o-mini')
        self.assertIn('492.65', sent['messages'][1]['content'])

    def test_openai_failure_becomes_explanation_unavailable(self):
        client, _ = fake_client(error=RuntimeError('quota exceeded'))
        with self.assertRaises(ExplanationUnavailable) as caught:
            OpenAICostExplainer('sk-test', client=client).explain(FACTS)
        self.assertIsInstance(caught.exception, AnalysisError)

    def test_empty_openai_answer_is_rejected(self):
        client, _ = fake_client('   ')
        with self.assertRaises(ExplanationUnavailable):
            OpenAICostExplainer('sk-test', client=client).explain(FACTS)

    def test_openai_is_only_used_with_a_real_looking_key(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}):
            self.assertEqual([type(e) for e in default_explainers()], [RuleBasedCostExplainer])
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'sk-test'}):
            self.assertEqual([type(e) for e in default_explainers()], [OpenAICostExplainer, RuleBasedCostExplainer])


class ExplainCostsTests(TestCase):
    def setUp(self):
        self.building = Building.objects.get(pk=bootstrap_demo()['building_id'])

    def test_falls_back_to_rules_when_openai_fails(self):
        client, _ = fake_client(error=RuntimeError('network down'))
        result = explain_costs(self.building, [OpenAICostExplainer('sk-test', client=client),
                                               RuleBasedCostExplainer()])
        self.assertTrue(result['available'])
        self.assertEqual(result['source'], 'RULE_BASED')
        self.assertEqual(result['fallback_reason'], 'openai_failed')
        self.assertIn('EUR', result['text'])

    def test_uses_openai_when_it_answers(self):
        client, _ = fake_client('Short AI explanation.')
        result = explain_costs(self.building, [OpenAICostExplainer('sk-test', client=client),
                                               RuleBasedCostExplainer()])
        self.assertEqual((result['source'], result['text']), ('OPENAI', 'Short AI explanation.'))

    def test_api_endpoint_works_without_a_key(self):
        client = APIClient()
        client.force_authenticate(get_user_model().objects.create_user(username='explain', password='pw12345'))
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}):
            response = client.post(f'/api/buildings/{self.building.pk}/cost/explain/', {}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['available'])
        self.assertEqual(response.data['source'], 'RULE_BASED')
        self.assertNotIn('facts', response.data)

    def test_api_requires_login(self):
        response = APIClient().post(f'/api/buildings/{self.building.pk}/cost/explain/', {}, format='json')
        self.assertIn(response.status_code, (401, 403))
