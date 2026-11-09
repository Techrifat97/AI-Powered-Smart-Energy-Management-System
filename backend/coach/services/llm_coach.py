import os
import json
import time
import logging
from django.core.serializers.json import DjangoJSONEncoder
from coach.models import AIRecommendation, LLMRequestLog

logger = logging.getLogger(__name__)


class RuleBasedCoachProvider:
    """
    Deterministic rule-based provider.
    Guarantees reliable, instant recommendations when OpenAI is offline, unconfigured, or out of quota.
    """

    @classmethod
    def generate(cls, building, summary: dict, forecast: list, target_savings_pct: float) -> list:
        peak_kw = summary['peak_demand_kw']
        solar_kwh = summary['total_solar_generated_kwh']
        daily_kwh = summary['average_daily_kwh']

        recommendations = []

        # Rule 1: Peak shaving if peak demand is high relative to daily average
        if peak_kw > (daily_kwh / 10.0):
            savings_kwh = 0.0  # A sampled peak alone cannot establish energy savings.
            recommendations.append({
                'title': 'Pre-Cooling & Peak Demand Shaving',
                'category': 'PEAK_SHAVING',
                'priority': 'HIGH',
                'suggested_action': (
                    f"Peak demand reached {peak_kw:.1f} kW. Pre-cool high-occupancy zones between 06:30 and 08:30 "
                    f"and investigate load scheduling. This sample does not establish energy or tariff savings."
                ),
                'estimated_savings_kwh': savings_kwh,
                'estimated_savings_eur': None,
                'confidence_score': 0.92,
                'source': 'RULE_BASED'
            })

        # Rule 2: Solar utilization if solar exists
        if solar_kwh > 0:
            savings_kwh = 0.0  # Load shifting does not establish a reduction in gross energy.
            recommendations.append({
                'title': 'Align Heavy Loads with Solar Peak',
                'category': 'RENEWABLE_SHIFT',
                'priority': 'MEDIUM',
                'suggested_action': (
                    f"Building produces {solar_kwh:.1f} kWh of solar. Shift heavy pump and ventilation cycles "
                    f"to 12:00-15:00 to maximize self-consumption and minimize grid draw."
                ),
                'estimated_savings_kwh': savings_kwh,
                'estimated_savings_eur': None,
                'confidence_score': 0.88,
                'source': 'RULE_BASED'
            })
        else:
            # Rule 2b: Lighting and standby audit
            savings_kwh = round(daily_kwh * 0.08 * 7, 2)
            recommendations.append({
                'title': 'Nighttime Standby & Lighting Setback',
                'category': 'LIGHTING',
                'priority': 'MEDIUM',
                'suggested_action': (
                    "Implement automatic setback schedules for corridor lighting and laboratory peripherals after 20:00. "
                    "Expected to eliminate phantom loads."
                ),
                'estimated_savings_kwh': savings_kwh,
                'estimated_savings_eur': None,
                'confidence_score': 0.85,
                'source': 'RULE_BASED'
            })

        # Rule 3: Behavioral target
        target_kwh = round(daily_kwh * (target_savings_pct / 100.0) * 7, 2)
        recommendations.append({
            'title': f'{int(target_savings_pct)}% Target Savings Behavioral Nudge',
            'category': 'BEHAVIORAL',
            'priority': 'LOW',
            'suggested_action': (
                f"To hit the user-requested {target_savings_pct}% weekly reduction goal, adjust thermostat deadbands "
                f"by +1°C in cooling season and -1°C in heating season across administrative offices."
            ),
            'estimated_savings_kwh': target_kwh,
            'estimated_savings_eur': None,
            'confidence_score': 0.81,
            'source': 'RULE_BASED'
        })

        return recommendations


class SustainabilityCoachService:
    """
    Main orchestration service for AI recommendations.
    Connects to OpenAI API using OPENAI_API_KEY from environment, with automatic fallback.
    """

    @classmethod
    def generate_recommendations(cls, building, summary: dict, forecast: list, target_savings_pct: float = 15.0) -> dict:
        api_key = os.getenv('OPENAI_API_KEY', '').strip()
        model_name = os.getenv('OPENAI_MODEL', 'gpt-4o-mini').strip()

        # Check if key is configured and not a placeholder
        is_key_configured = bool(api_key and not api_key.startswith('your-') and api_key.startswith('sk-'))

        recommendations_data = []
        source_used = 'RULE_BASED'
        tokens_info = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
        latency_ms = 0
        status_log = 'FALLBACK'
        error_msg = ''

        if is_key_configured:
            start_time = time.time()
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)

                # Prepare concise prompt context
                prompt_context = {
                    'building_name': building.name,
                    'area_sqm': building.area_sqm,
                    'baseline_kwh_per_day': building.baseline_kwh_per_day,
                    'summary': summary,
                    'forecast_next_7_days': forecast[:3], # compact summary
                    'target_savings_pct': target_savings_pct
                }

                system_prompt = (
                    "You are an expert Smart Energy Management AI Coach for European university and commercial buildings. "
                    "Analyze the building's telemetry and 7-day forecast. Return exactly 3 specific, high-impact "
                    "actionable recommendations formatted as a valid JSON array of objects with keys: "
                    "'title' (string), 'category' (one of: PEAK_SHAVING, HVAC_OPTIMIZATION, LIGHTING, RENEWABLE_SHIFT, BEHAVIORAL), "
                    "'priority' (HIGH, MEDIUM, or LOW), 'suggested_action' (string), "
                    "'estimated_savings_kwh' (float, illustrative weekly scenario), "
                    "'confidence_score' (float between 0.75 and 0.98). "
                    "Return ONLY the raw JSON array without markdown formatting or code fences."
                )

                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(prompt_context, cls=DjangoJSONEncoder)}
                    ],
                    temperature=0.3,
                    max_tokens=600,
                )

                latency_ms = int((time.time() - start_time) * 1000)
                raw_content = response.choices[0].message.content.strip()

                # Clean potential markdown fences
                if raw_content.startswith('```'):
                    raw_content = raw_content.strip('`').lstrip('json').strip()

                parsed_recs = json.loads(raw_content)
                if isinstance(parsed_recs, list) and len(parsed_recs) > 0:
                    for rec in parsed_recs:
                        rec['source'] = 'OPENAI'
                    recommendations_data = parsed_recs
                    source_used = 'OPENAI'
                    status_log = 'SUCCESS'

                if hasattr(response, 'usage') and response.usage:
                    tokens_info['prompt_tokens'] = response.usage.prompt_tokens
                    tokens_info['completion_tokens'] = response.usage.completion_tokens
                    tokens_info['total_tokens'] = response.usage.total_tokens

            except Exception as e:
                logger.warning(f"OpenAI call failed, activating rule-based fallback: {str(e)}")
                error_msg = str(e)
                status_log = 'FAILED_FALLBACK'
                latency_ms = int((time.time() - start_time) * 1000) if 'start_time' in locals() else 0

        # If OpenAI wasn't used or failed, use rule-based provider
        if not recommendations_data:
            recommendations_data = RuleBasedCoachProvider.generate(
                building=building,
                summary=summary,
                forecast=forecast,
                target_savings_pct=target_savings_pct
            )

        # Log LLM Telemetry
        LLMRequestLog.objects.create(
            model_name=model_name if source_used == 'OPENAI' else 'rule-based-engine',
            prompt_tokens=tokens_info['prompt_tokens'],
            completion_tokens=tokens_info['completion_tokens'],
            total_tokens=tokens_info['total_tokens'],
            latency_ms=latency_ms,
            status=status_log,
            error_message=error_msg
        )

        # Persist recommendations to database
        saved_recs = []
        for r in recommendations_data:
            obj = AIRecommendation.objects.create(
                building=building,
                title=r.get('title', 'Optimization Action'),
                category=r.get('category', 'PEAK_SHAVING'),
                priority=r.get('priority', 'MEDIUM'),
                suggested_action=r.get('suggested_action', ''),
                estimated_savings_kwh=float(r.get('estimated_savings_kwh', 0.0)),
                estimated_savings_eur=None,  # No timed action or applicable tariff is established.
                confidence_score=float(r.get('confidence_score', 0.85)),
                source=r.get('source', source_used),
                status='PENDING'
            )
            saved_recs.append(obj)

        return {
            'source': source_used,
            'status': status_log,
            'tokens': tokens_info,
            'latency_ms': latency_ms,
            'recommendations': saved_recs
        }

