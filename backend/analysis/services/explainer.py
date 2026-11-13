"""Plain-language explanation of a building's electricity costs.

`OpenAICostExplainer` asks an OpenAI model to explain the numbers to a non-expert.
`RuleBasedCostExplainer` writes the same kind of text from templates and always
works, so the feature never depends on an API key or the network. Both share the
abstract `CostExplainer` interface; `explain_costs()` tries them in order.
"""
import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime

from .costs import cost_analysis
from .errors import ExplanationUnavailable
from .scenarios import run_scenario

logger = logging.getLogger(__name__)

TIP_REDUCTION_PCT = 10


def _days_between(first, last):
    if not first or not last:
        return None
    if isinstance(first, str):
        first, last = datetime.fromisoformat(first), datetime.fromisoformat(last)
    return max((last - first).total_seconds() / 86400, 1 / 24)


def build_cost_facts(building):
    """Collect the numbers an explanation may use. Returns None when costs are unavailable."""
    cost = cost_analysis(building)
    if not cost['cost_estimates_available']:
        return None
    summary = cost['energy_summary']
    days = _days_between(summary.get('earliest_reading'), summary.get('latest_reading'))
    net = cost['estimated_net_cost_eur']
    facts = {
        'building_name': building.name,
        'location': building.location or None,
        'tariff_name': cost['tariff_applied'],
        'price_eur_per_kwh': cost['rate_eur_per_kwh'],
        'days_measured': round(days, 1) if days else None,
        'net_cost_eur': net,
        'cost_per_day_eur': round(net / days, 2) if days else None,
        'grid_import_kwh': round(cost['estimated_grid_import_kwh'] or 0, 1),
        'grid_import_cost_eur': cost['estimated_import_cost_eur'],
        'solar_generated_kwh': round(cost['solar_generated_kwh'] or 0, 1),
        'solar_export_kwh': round(cost['estimated_grid_export_kwh'] or 0, 1),
        'solar_export_credit_eur': cost['estimated_export_credit_eur'],
        'baseline_kwh_per_day': building.baseline_kwh_per_day,
        'saving_if_10pct_less_eur': None,
        'saving_period_days': None,
    }
    scenario = run_scenario(building, consumption_change_pct=-TIP_REDUCTION_PCT)
    if scenario['available']:
        facts['saving_if_10pct_less_eur'] = round(-scenario['difference_net_cost_eur'], 2)
        if scenario.get('period_start'):
            start = datetime.fromisoformat(scenario['period_start'])
            end = datetime.fromisoformat(scenario['period_end'])
            facts['saving_period_days'] = (end - start).days + 1
    return facts


class CostExplainer(ABC):
    """Turns cost facts into a short text for people without technical knowledge."""

    source = ''

    @abstractmethod
    def explain(self, facts):
        """Return the explanation text or raise ExplanationUnavailable."""


class RuleBasedCostExplainer(CostExplainer):
    """Template-based explanation; needs no network and never fails on valid facts."""

    source = 'RULE_BASED'

    def explain(self, facts):
        parts = []
        period = f"over the last {facts['days_measured']:g} days" if facts.get('days_measured') else 'so far'
        line = f"You paid about {facts['net_cost_eur']:,.2f} EUR for electricity {period}"
        if facts.get('cost_per_day_eur') is not None:
            line += f", which is about {facts['cost_per_day_eur']:,.2f} EUR a day"
        parts.append(line + '.')
        parts.append(f"Almost all of it is for {facts['grid_import_kwh']:,.0f} kWh of electricity bought from "
                     f"the grid ({facts['grid_import_cost_eur']:,.2f} EUR).")
        if facts.get('solar_generated_kwh'):
            parts.append(f"Your solar panels made {facts['solar_generated_kwh']:,.0f} kWh. Most of it was used "
                         f"in the building for free, and the surplus earned you "
                         f"{facts['solar_export_credit_eur']:,.2f} EUR.")
        if facts.get('saving_if_10pct_less_eur'):
            days = facts.get('saving_period_days')
            parts.append(f"Using {TIP_REDUCTION_PCT}% less electricity would have saved about "
                         f"{facts['saving_if_10pct_less_eur']:,.2f} EUR"
                         + (f" in {days} days." if days else '.'))
        parts.append('Easy ways to save: switch off lights and computers in empty rooms, lower the heating by '
                     'one degree, and check the Alerts page for devices that run at night.')
        return ' '.join(parts)


class OpenAICostExplainer(CostExplainer):
    """Asks an OpenAI chat model for the explanation. `client` can be injected for tests."""

    source = 'OPENAI'
    SYSTEM_PROMPT = (
        'You explain the electricity costs of a building to a person with no technical knowledge. '
        'Use simple, friendly English and at most 120 words. Say what they paid and why, mention the '
        'solar panels if there are any, and give two concrete, practical tips to pay less. '
        'Use ONLY the numbers in the data you are given and never invent figures. '
        'Write plain sentences: no headings, no tables and no markdown.'
    )

    def __init__(self, api_key, model='gpt-4o-mini', client=None):
        self.api_key = api_key
        self.model = model
        self._client = client

    @classmethod
    def from_environment(cls):
        """Return an explainer when a real-looking key is configured, else None."""
        key = os.getenv('OPENAI_API_KEY', '').strip()
        if not key.startswith('sk-'):
            return None
        return cls(key, os.getenv('OPENAI_MODEL', 'gpt-4o-mini').strip() or 'gpt-4o-mini')

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key, timeout=12, max_retries=0)
        return self._client

    def explain(self, facts):
        try:
            response = self._get_client().chat.completions.create(
                model=self.model,
                messages=[{'role': 'system', 'content': self.SYSTEM_PROMPT},
                          {'role': 'user', 'content': json.dumps(facts)}],
                temperature=0.3,
                max_tokens=300,
            )
            text = (response.choices[0].message.content or '').strip()
        except Exception as error:  # network, auth, quota, malformed response
            raise ExplanationUnavailable(f'openai_failed: {error}') from error
        if not text:
            raise ExplanationUnavailable('openai_empty_answer')
        return text


def default_explainers():
    openai_explainer = OpenAICostExplainer.from_environment()
    return [e for e in (openai_explainer, RuleBasedCostExplainer()) if e is not None]


def explain_costs(building, explainers=None):
    """Explain a building's costs with the first explainer that succeeds."""
    facts = build_cost_facts(building)
    if facts is None:
        return {'available': False, 'reason': cost_analysis(building)['cost_estimates_reason'],
                'text': None, 'source': None}
    fallback_reason = None
    for explainer in explainers if explainers is not None else default_explainers():
        try:
            return {'available': True, 'reason': 'available', 'text': explainer.explain(facts),
                    'source': explainer.source, 'fallback_reason': fallback_reason, 'facts': facts}
        except ExplanationUnavailable as error:
            logger.warning('Cost explanation fell back: %s', error)
            fallback_reason = str(error).split(':')[0]
    return {'available': False, 'reason': 'no_explainer_available', 'text': None, 'source': None}
