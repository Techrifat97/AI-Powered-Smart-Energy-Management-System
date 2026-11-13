"""Small PostgreSQL examples for synthetic history and OOP contracts."""
from datetime import datetime, timezone, timedelta
from inspect import isgenerator
from unittest.mock import patch

from django.test import TestCase, SimpleTestCase
from django.core.exceptions import ValidationError
from monitoring.models import Building, Meter, EnergyReading
from monitoring.services.demo import bootstrap_demo, ensure_inventory
from monitoring.services.profiles import (EnergyProfile, EnergyQuantity, TelemetryGenerator,
    ElectricityProfile, HVACProfile, LightingProfile, SolarProfile, ProfileContext)
from monitoring.services.aggregation import building_energy_report


class ProfileTests(SimpleTestCase):
    def test_abstract_and_value_contract(self):
        with self.assertRaises(TypeError):
            EnergyProfile()
        self.assertEqual((EnergyQuantity(2) + EnergyQuantity(3)).kwh, 5)
        with self.assertRaises(TypeError):
            EnergyQuantity(2) + 3
        with self.assertRaises(ValueError):
            EnergyQuantity(float('nan'))
        with self.assertRaises(Exception):
            EnergyQuantity(2).kwh = 4

    def test_profiles_and_dispatch(self):
        from types import SimpleNamespace as Obj
        ts = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
        meters = [Obj(pk=i, meter_type=k, device_id=str(i)) for i,k in enumerate(
            ['ELECTRICITY','HVAC','HVAC','LIGHTING','LIGHTING','SOLAR'],1)]
        gen = TelemetryGenerator()
        stream = gen.iter_readings(Obj(pk=1), meters, ts)
        self.assertTrue(isgenerator(stream))
        rows = list(stream)
        self.assertEqual(rows[0]['power_kw'],12.971)  # Golden v1 SHA-256 fixture.
        self.assertEqual(rows, list(gen.iter_readings(Obj(pk=1),meters,ts)))
        self.assertAlmostEqual(rows[1]['power_kw'] + rows[2]['power_kw'],
                               (int(rows[0]['power_kw'] * 1000) * 30 // 100) // 2 * 2 / 1000)
        self.assertLess(rows[3]['power_kw'] + rows[4]['power_kw'],rows[0]['power_kw'])
        self.assertEqual(rows[5]['power_kw'],10)
        context=ProfileContext(1,ts,'x',2,2,12000)
        self.assertEqual(HVACProfile().calculate_power(context),1800)
        self.assertEqual(LightingProfile().calculate_power(context),900)
        self.assertEqual(SolarProfile().calculate_power(context),10000)
        self.assertEqual(SolarProfile().calculate_power(ProfileContext(1,ts.replace(hour=0),'x',0,0)),0)
        self.assertIsInstance(ElectricityProfile().calculate_power(context),int)

    def test_injected_strategy_is_used_polymorphically(self):
        from types import SimpleNamespace as Obj
        class FixedMain(EnergyProfile):
            def calculate_power(self, context):
                return 20000
        simulator = TelemetryGenerator({'ELECTRICITY': FixedMain(), 'HVAC': HVACProfile()})
        meters = [Obj(pk=1, meter_type='ELECTRICITY', device_id='m'),
                  Obj(pk=2, meter_type='HVAC', device_id='h')]
        rows = list(simulator.iter_readings(Obj(pk=1), meters,
                    datetime(2026,11,9,12,tzinfo=timezone.utc)))
        self.assertEqual([row['power_kw'] for row in rows], [20, 6])


class BootstrapTests(TestCase):
    def setUp(self):
        self.now = datetime(2026,11,12,12,tzinfo=timezone.utc)

    def test_full_history_and_restart_rename(self):
        result=bootstrap_demo(now=self.now)
        self.assertEqual(result['created'],1344)
        building=Building.objects.get(pk=result['building_id'])
        self.assertEqual(building.meters.count(),4)
        report=building_energy_report(building)
        self.assertEqual(len(report['complete_days']),14)
        self.assertTrue(report['summary']['grid_estimates_available'])
        self.assertTrue(report['summary']['main_coverage_complete'])
        rows=list(EnergyReading.objects.order_by('pk').values())
        building.name='Professor custom name';building.save()
        self.assertEqual(ensure_inventory()[0].pk,building.pk)
        self.assertEqual(bootstrap_demo(now=self.now)['created'],0)
        self.assertEqual(rows,list(EnergyReading.objects.order_by('pk').values()))
        self.assertEqual(building.meters.filter(readings__energy_kwh=0,meter_type='SOLAR').distinct().count(),1)

    def test_existing_history_adopted_without_repair(self):
        building,_=ensure_inventory()
        EnergyReading.objects.create(meter=building.meters.first(),timestamp=self.now-timedelta(days=2),energy_kwh=3)
        self.assertEqual(bootstrap_demo(now=self.now)['status'],'adopted_existing_history_without_backfill')
        self.assertEqual(EnergyReading.objects.count(),1)

    def test_normal_building_stays_empty(self):
        other=Building.objects.create(name='Real user building')
        bootstrap_demo(now=self.now)
        self.assertFalse(EnergyReading.objects.filter(meter__building=other).exists())

    def test_atomic_failure(self):
        with patch('monitoring.services.profiles.TelemetryGenerator.iter_readings',side_effect=ValueError('broken')):
            with self.assertRaises(ValueError): bootstrap_demo(now=self.now)
        self.assertFalse(Building.objects.exists())

    def test_s2_and_s3_ready_without_openai(self):
        from rest_framework.test import APIClient
        from django.utils import timezone as django_timezone
        from django.contrib.auth.models import User
        result=bootstrap_demo(now=django_timezone.now())
        client=APIClient();bid=result['building_id']
        user=User.objects.filter(username='admin').first() or User.objects.create_user('testadmin','a@b.com','pw')
        client.force_authenticate(user=user)
        forecast=client.get(f'/api/buildings/{bid}/forecast/')
        self.assertEqual(forecast.status_code,200)
        self.assertEqual(len(forecast.data['forecast']),7)
        with patch.dict('os.environ',{'OPENAI_API_KEY':''}):
            recommendation=client.post('/api/recommendations/generate/',{'building_id':bid},format='json')
        self.assertEqual(recommendation.status_code,201)
        self.assertTrue(recommendation.data['availability']['available'])
        self.assertTrue(recommendation.data['recommendations'])
        self.assertTrue(recommendation.data['sustainability_assessment'])
        cost=client.get(f'/api/buildings/{bid}/cost/')
        self.assertTrue(cost.data['cost_estimates_available'])
        report=client.post(f'/api/buildings/{bid}/reports/',
            {k:result[k] for k in ('period_start','period_end')},format='json')
        self.assertEqual(report.status_code,201)

    def test_refresh_fills_only_empty_days_preserving_old_records(self):
        first=bootstrap_demo(now=self.now)
        rows=list(EnergyReading.objects.order_by('pk').values())
        result=bootstrap_demo(now=self.now+timedelta(days=2),refresh=True)
        self.assertEqual(result['created'],192)
        self.assertEqual(rows,list(EnergyReading.objects.filter(pk__lte=rows[-1]['id']).order_by('pk').values()))
        self.assertEqual(bootstrap_demo(now=self.now+timedelta(days=2),refresh=True)['created'],0)

    def test_refresh_skips_partial_live_day(self):
        first=bootstrap_demo(now=self.now)
        building=Building.objects.get(pk=first['building_id'])
        EnergyReading.objects.create(meter=building.meters.first(),timestamp=self.now,interval_seconds=60,energy_kwh=1)
        result=bootstrap_demo(now=self.now+timedelta(days=1),refresh=True)
        self.assertEqual(result['created'],0)
        self.assertEqual(EnergyReading.objects.count(),1345)

    def test_tariff_setup_preserves_inactive_records_and_later_user_choice(self):
        from analysis.models import TariffPlan
        old=TariffPlan.objects.create(name='User inactive',is_active=False,rate_standard_eur_per_kwh=.77)
        bootstrap_demo(now=self.now)
        self.assertEqual(TariffPlan.objects.filter(is_active=True).count(),1)
        old.refresh_from_db();self.assertEqual(old.rate_standard_eur_per_kwh,.77)
        self.assertFalse(old.is_active)
        TariffPlan.objects.filter(is_active=True).update(is_active=False)
        bootstrap_demo(now=self.now)
        self.assertFalse(TariffPlan.objects.filter(is_active=True).exists())
