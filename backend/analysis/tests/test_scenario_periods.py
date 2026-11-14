"""Inclusive UTC scenario windows retain existing quality checks."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from monitoring.models import Building, EnergyReading
from monitoring.services.demo import bootstrap_demo


class ScenarioPeriodTests(TestCase):
    def setUp(self):
        self.result=bootstrap_demo()
        self.building=Building.objects.get(pk=self.result['building_id'])
        self.url=f'/api/buildings/{self.building.pk}/scenarios/'
        self.client=APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username='scenario_user', password='password123')
        self.client.force_authenticate(user=self.user)
        self.body={k:self.result[k] for k in ('period_start','period_end')}

    def test_complete_history_still_works_after_live_gap(self):
        main=self.building.meters.get(meter_type='ELECTRICITY')
        solar=self.building.meters.get(meter_type='SOLAR')
        minute=timezone.now().replace(second=0,microsecond=0)-timedelta(minutes=1)
        for meter,energy in [(main,2),(solar,1)]:
            EnergyReading.objects.create(meter=meter,timestamp=minute,interval_seconds=60,energy_kwh=energy)
        response=self.client.post(self.url,self.body,format='json')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.data['available'])
        self.assertEqual(response.data['period_start'],self.body['period_start'])
        self.assertEqual(response.data['baseline'],response.data['scenario'])
        # Without dates the latest complete days are chosen automatically, so the live gap
        # no longer makes the default scenario unavailable.
        automatic=self.client.post(self.url,{},format='json')
        self.assertTrue(automatic.data['available'])
        self.assertTrue(automatic.data['period_auto'])
        self.assertEqual(automatic.data['period_start'],self.body['period_start'])
        self.assertEqual(automatic.data['period_end'],self.body['period_end'])

    def test_same_period_used_for_modified_price(self):
        body=dict(self.body,consumption_change_pct=-100,solar_change_pct=-100)
        response=self.client.post(self.url,body,format='json')
        self.assertTrue(response.data['available'])
        self.assertGreater(response.data['baseline']['net_cost_eur'],0)
        self.assertEqual(response.data['scenario']['net_cost_eur'],0)

    def test_bad_dates_and_percentages(self):
        for body in ({'period_start':self.body['period_start']}, {'period_end':self.body['period_end']},
                     {'period_start':'bad','period_end':self.body['period_end']},
                     {'period_start':self.body['period_end'],'period_end':self.body['period_start']},
                     {'period_start':'9999-12-31','period_end':'9999-12-31'},
                     {'consumption_change_pct':'NaN'}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post(self.url,body,format='json').status_code,400)

    def test_missing_main_or_solar_not_zero_filled(self):
        first=EnergyReading.objects.filter(meter__building=self.building,meter__meter_type='ELECTRICITY').earliest('timestamp')
        first.delete()  # Disposable test fixture only.
        response=self.client.post(self.url,self.body,format='json')
        self.assertFalse(response.data['available'])

    def test_missing_solar_alignment_rejected(self):
        first=EnergyReading.objects.filter(meter__building=self.building,meter__meter_type='SOLAR').earliest('timestamp')
        first.delete()
        response=self.client.post(self.url,self.body,format='json')
        self.assertFalse(response.data['available'])

    def test_period_outside_data_rejected(self):
        response=self.client.post(self.url,{'period_start':'2000-01-01','period_end':'2000-01-01'},format='json')
        self.assertFalse(response.data['available'])
