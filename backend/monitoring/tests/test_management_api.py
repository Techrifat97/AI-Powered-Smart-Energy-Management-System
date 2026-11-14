"""Management/history contracts and PostgreSQL inventory races."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase
from django.urls import resolve, reverse
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from monitoring.models import Building, EnergyReading, Meter
from monitoring.services.generator import generate_minute


class ManagementAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username='mgmt_user', password='password123')
        self.client.force_authenticate(user=self.user)
        self.building = Building.objects.create(name='API lab', has_solar_installation=False)
        self.solar_building = Building.objects.create(name='PV lab', has_solar_installation=True)
        self.minute = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)

    def meters_url(self, building=None):
        return reverse('building-meter-list', args=[(building or self.building).pk])

    def meter(self, *, building=None, kind='ELECTRICITY', active=True, device_id='API-MAIN'):
        return Meter.objects.create(building=building or self.building, device_id=device_id,
                                    meter_type=kind, is_active=active)

    def patch_meter(self, meter, **values):
        return self.client.patch(reverse('meter-detail', args=[meter.pk]), values, format='json')

    def test_building_creation_requires_explicit_solar_status_and_creates_no_meters(self):
        url = reverse('building-list')
        for flag in [True, False]:
            response = self.client.post(url, dict(name='New building', has_solar_installation=flag,
                area_sqm=1500, baseline_kwh_per_day=0), format='json')
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.data['has_solar_installation'], flag)
            self.assertEqual(response.data['meters'], [])
        self.assertFalse(Meter.objects.exists())
        for data in [{'name': 'Missing flag'}, {'name': 'Null flag', 'has_solar_installation': None}]:
            response = self.client.post(url, data, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertIn('has_solar_installation', response.data)
        form = self.client.post(url, {'name': 'Missing form checkbox'}, format='multipart')
        self.assertEqual(form.status_code, 400)
        self.assertIn('has_solar_installation', form.data)

    def test_building_model_numeric_validation_is_used(self):
        for field, values in [('area_sqm', [0, -1, 'NaN', 'Infinity', '1e309', 'bad']),
                              ('baseline_kwh_per_day', [-1, 'NaN', '-Infinity', 'bad'])]:
            for value in values:
                with self.subTest(field=field, value=value):
                    before = Building.objects.count()
                    response = self.client.post(reverse('building-list'),
                        dict(name='Invalid', has_solar_installation=False, **{field: value}), format='json')
                    self.assertEqual(response.status_code, 400)
                    self.assertIn(field, response.data)
                    self.assertEqual(Building.objects.count(), before)

    def test_descriptive_update_and_existing_read_response_fields(self):
        url = reverse('building-detail', args=[self.building.pk])
        response = self.client.patch(url, {'name': 'Renamed', 'location': 'Room 4', 'area_sqm': 120}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Renamed')
        self.assertTrue({'id', 'name', 'location', 'area_sqm', 'baseline_kwh_per_day',
                         'has_solar_installation', 'meters', 'created_at'}.issubset(response.data))
        response = self.client.put(url, {'name': 'Full update', 'has_solar_installation': False}, format='json')
        self.assertEqual(response.status_code, 200)
        invalid = self.client.patch(url, {'area_sqm': -1}, format='json')
        self.assertEqual(invalid.status_code, 400)
        self.building.refresh_from_db()
        self.assertEqual(self.building.area_sqm, 120)

    def test_solar_metadata_changes_before_history_allow_stepwise_setup(self):
        url = reverse('building-detail', args=[self.building.pk])
        self.assertEqual(self.client.patch(url, {'has_solar_installation': True}, format='json').status_code, 200)
        # No solar meter is required yet: inventory can be assembled step by step.
        response = self.client.post(self.meters_url(), {'device_id': 'PV-NEW', 'meter_type': 'SOLAR'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.patch_meter(Meter.objects.get(pk=response.data['id']), is_active=False)
        response = self.client.patch(url, {'has_solar_installation': False}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('has_solar_installation', response.data)

    def test_any_reading_freezes_solar_meaning_but_not_descriptive_fields(self):
        meter = self.meter()
        EnergyReading.objects.create(meter=meter, timestamp=self.minute, energy_kwh=0, interval_seconds=60)
        url = reverse('building-detail', args=[self.building.pk])
        response = self.client.patch(url, {'has_solar_installation': True}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('has_solar_installation', response.data)
        response = self.client.patch(url, {'name': 'Still editable', 'has_solar_installation': False}, format='json')
        self.assertEqual(response.status_code, 200)
        self.building.refresh_from_db()
        self.assertIs(self.building.has_solar_installation, False)

    def test_legacy_unknown_solar_status_is_readable_but_not_implicitly_repaired(self):
        self.building.has_solar_installation = None
        self.building.save()
        meter = self.meter()
        EnergyReading.objects.create(meter=meter, timestamp=self.minute, energy_kwh=1, interval_seconds=None)
        url = reverse('building-detail', args=[self.building.pk])
        self.assertIsNone(self.client.get(url).data['has_solar_installation'])
        self.assertEqual(self.client.patch(url, {'location': 'Lab'}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(url, {'has_solar_installation': True}, format='json').status_code, 400)

    def test_meter_create_is_bound_to_url_building_and_list_is_isolated(self):
        self.meter(building=self.solar_building, device_id='OTHER')
        response = self.client.post(self.meters_url(), {'device_id': 'HVAC', 'meter_type': 'HVAC'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['building'], self.building.pk)
        self.assertEqual(response.data['unit'], 'kWh')
        result = self.client.get(self.meters_url()).data
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['results'][0]['device_id'], 'HVAC')
        form = self.client.post(self.meters_url(), {'device_id': 'FORM-HVAC', 'meter_type': 'HVAC'}, format='multipart')
        self.assertEqual(form.status_code, 201)
        self.assertTrue(form.data['is_active'])
        response = self.client.post(self.meters_url(), {'device_id': 'SPOOF', 'building': self.solar_building.pk}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('building', response.data)

    def test_duplicate_device_id_returns_field_error(self):
        self.meter()
        response = self.client.post(self.meters_url(self.solar_building), {'device_id': 'API-MAIN'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('device_id', response.data)
        self.assertEqual(Meter.objects.count(), 1)

    def test_meter_type_and_unit_validation(self):
        for field, value in [('meter_type', 'GAS'), ('unit', 'Wh'), ('device_id', '')]:
            with self.subTest(field=field):
                payload = dict(device_id='INVALID')
                payload[field] = value
                response = self.client.post(self.meters_url(), payload, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
        self.assertFalse(Meter.objects.exists())

    def test_solar_creation_requires_true_even_for_inactive_meter(self):
        for flag in [False, None]:
            Building.objects.filter(pk=self.building.pk).update(has_solar_installation=flag)
            for active in [True, False]:
                response = self.client.post(self.meters_url(), dict(device_id='PV', meter_type='SOLAR', is_active=active), format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('meter_type', response.data)
        response = self.client.post(self.meters_url(self.solar_building), dict(device_id='PV', meter_type='SOLAR'), format='json')
        self.assertEqual(response.status_code, 201)

    def test_creation_blocks_multiple_active_main_and_solar_but_allows_inactive_spares(self):
        for kind, building in [('ELECTRICITY', self.building), ('SOLAR', self.solar_building)]:
            with self.subTest(kind=kind):
                url = self.meters_url(building)
                self.assertEqual(self.client.post(url, dict(device_id=f'{kind}-1', meter_type=kind), format='json').status_code, 201)
                response = self.client.post(url, dict(device_id=f'{kind}-2', meter_type=kind), format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('is_active', response.data)
                self.assertEqual(self.client.post(url, dict(device_id=f'{kind}-3', meter_type=kind, is_active=False), format='json').status_code, 201)

    def test_activation_conflicts_and_deactivation_are_field_errors_or_allowed(self):
        for kind, building in [('ELECTRICITY', self.building), ('SOLAR', self.solar_building)]:
            first = self.meter(building=building, kind=kind, device_id=f'{kind}-FIRST')
            spare = self.meter(building=building, kind=kind, active=False, device_id=f'{kind}-SPARE')
            conflict = self.patch_meter(spare, is_active=True)
            self.assertEqual(conflict.status_code, 400)
            self.assertIn('is_active', conflict.data)
            self.assertEqual(self.patch_meter(first, is_active=False).status_code, 200)
            self.assertEqual(self.patch_meter(spare, is_active=True).status_code, 200)

    def test_submeter_deactivation_reactivation_retains_history(self):
        meter = self.meter(kind='HVAC')
        row = EnergyReading.objects.create(meter=meter, timestamp=self.minute, energy_kwh=5, interval_seconds=60)
        for active in [False, True]:
            response = self.patch_meter(meter, is_active=active)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['is_active'], active)
            self.assertTrue(EnergyReading.objects.filter(pk=row.pk, energy_kwh=5).exists())

    def test_solar_deactivation_is_allowed_with_bad_legacy_metadata_but_activation_is_not(self):
        solar = self.meter(kind='SOLAR')  # Deliberately bypass the API for a legacy contradiction.
        self.assertEqual(self.patch_meter(solar, is_active=False).status_code, 200)
        response = self.patch_meter(solar, is_active=True)
        self.assertEqual(response.status_code, 400)
        self.assertIn('is_active', response.data)

    def test_historical_meter_identity_is_immutable_and_no_hard_delete_or_reading_writes(self):
        meter = self.meter()
        row = EnergyReading.objects.create(meter=meter, timestamp=self.minute, energy_kwh=1)
        url = reverse('meter-detail', args=[meter.pk])
        for field, value in [('building', self.solar_building.pk), ('device_id', 'RENAMED'),
                             ('meter_type', 'HVAC'), ('unit', 'Wh'), ('created_at', self.minute.isoformat())]:
            response = self.client.patch(url, {field: value}, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.data)
        for method in ['put', 'delete']:
            self.assertEqual(getattr(self.client, method)(url, {}, format='json').status_code, 405)
        self.assertEqual(self.client.delete(reverse('building-detail', args=[self.building.pk])).status_code, 405)
        history = reverse('building-readings', args=[self.building.pk])
        self.assertEqual(self.client.post(history, {}, format='json').status_code, 405)
        self.assertEqual(self.client.patch(history, {}, format='json').status_code, 405)
        self.assertEqual(self.client.delete(history).status_code, 405)
        meter.refresh_from_db()
        self.assertEqual((meter.device_id, meter.meter_type, meter.building_id), ('API-MAIN', 'ELECTRICITY', self.building.pk))
        self.assertTrue(EnergyReading.objects.filter(pk=row.pk).exists())

    def test_resources_return_404_and_both_route_prefixes_work(self):
        meter = self.meter()
        for path in [f'/api/buildings/{self.building.pk}/', f'/api/monitoring/buildings/{self.building.pk}/',
                     f'/api/meters/{meter.pk}/', f'/api/monitoring/meters/{meter.pk}/']:
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get('/api/meters/999999/').status_code, 404)
        self.assertEqual(self.client.get('/api/buildings/999999/meters/').status_code, 404)
        self.assertEqual(self.client.post('/api/buildings/999999/meters/', {'device_id': 'MISSING'}, format='json').status_code, 404)


class ReadingHistoryAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username='history_user', password='password123')
        self.client.force_authenticate(user=self.user)
        self.building = Building.objects.create(name='History lab', has_solar_installation=False)
        self.main = Meter.objects.create(building=self.building, device_id='HISTORY-MAIN', is_active=False)
        self.sub = Meter.objects.create(building=self.building, device_id='HISTORY-HVAC', meter_type='HVAC')
        other = Building.objects.create(name='Private other building')
        self.other = Meter.objects.create(building=other, device_id='OTHER')
        self.start = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
        self.url = reverse('building-readings', args=[self.building.pk])

    def reading(self, meter, timestamp=None, duration=60):
        return EnergyReading.objects.create(meter=meter, timestamp=timestamp or self.start,
            interval_seconds=duration, energy_kwh=1, power_kw=3, voltage=230)

    def test_history_keeps_inactive_readings_and_explicit_legacy_unknown_duration(self):
        row = self.reading(self.main, duration=None)
        self.reading(self.other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        result = response.data['results'][0]
        self.assertEqual(result['id'], row.pk)
        self.assertEqual(result['meter'], self.main.pk)
        self.assertEqual(result['meter_device_id'], 'HISTORY-MAIN')
        self.assertEqual(result['meter_type'], 'ELECTRICITY')
        self.assertEqual(result['meter_unit'], 'kWh')
        self.assertIsNone(result['interval_seconds'])
        self.assertTrue({'timestamp', 'energy_kwh', 'power_kw', 'voltage'}.issubset(result))

    def test_half_open_filters_use_interval_start_and_support_offsets(self):
        self.reading(self.main, self.start - timedelta(minutes=1), duration=3600)
        first = self.reading(self.main)
        inside = self.reading(self.main, self.start + timedelta(minutes=1))
        self.reading(self.main, self.start + timedelta(minutes=2))
        for start in [self.start.isoformat(), '2026-11-09T14:00:00+02:00']:
            response = self.client.get(self.url, {'start': start, 'end': '2026-11-09T12:02:00Z'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual([r['id'] for r in response.data['results']], [inside.pk, first.pk])
        self.assertEqual(self.client.get(self.url, {'end': self.start.isoformat()}).data['count'], 1)
        self.assertEqual(self.client.get(self.url, {'start': self.start.isoformat()}).data['count'], 3)

    def test_invalid_naive_and_reversed_bounds_have_field_errors(self):
        for field in ['start', 'end']:
            for value in ['bad', '2026-11-09', '2026-11-09T12:00:00', '', '2026-02-30T12:00:00Z']:
                with self.subTest(field=field, value=value):
                    response = self.client.get(self.url, {field: value})
                    self.assertEqual(response.status_code, 400)
                    self.assertIn(field, response.data)
        for end in ['2026-11-09T12:00:00Z', '2026-11-09T11:59:00Z']:
            response = self.client.get(self.url, {'start': self.start.isoformat(), 'end': end})
            self.assertEqual(response.status_code, 400)
            self.assertIn('end', response.data)

    def test_specific_meter_must_belong_to_requested_building(self):
        row = self.reading(self.main)
        self.reading(self.sub)
        self.reading(self.other)
        response = self.client.get(self.url, {'meter_id': self.main.pk})
        self.assertEqual([r['id'] for r in response.data['results']], [row.pk])
        self.assertEqual(self.client.get(self.url, {'meter_id': self.other.pk}).status_code, 404)
        self.assertEqual(self.client.get(self.url, {'meter_id': 999999}).status_code, 404)
        for value in ['bad', '-1', '0', '1.2']:
            response = self.client.get(self.url, {'meter_id': value})
            self.assertEqual(response.status_code, 400)
            self.assertIn('meter_id', response.data)
        self.assertEqual(self.client.get('/api/buildings/999999/readings/').status_code, 404)

    def test_pagination_has_stable_timestamp_id_order_and_no_per_row_queries(self):
        first = self.reading(self.main)
        second = self.reading(self.sub)
        newest = self.reading(self.main, self.start + timedelta(minutes=1))
        with self.assertNumQueries(3):
            page1 = self.client.get(self.url, {'page_size': 2})
        page2 = self.client.get(self.url, {'page_size': 2, 'page': 2})
        self.assertEqual(page1.data['count'], 3)
        self.assertEqual([r['id'] for r in page1.data['results']], [newest.pk, second.pk])
        self.assertEqual([r['id'] for r in page2.data['results']], [first.pk])
        self.assertIsNotNone(page1.data['next'])
        self.assertIsNotNone(page2.data['previous'])

    def test_page_size_is_bounded(self):
        EnergyReading.objects.bulk_create([EnergyReading(meter=self.main,
            timestamp=self.start + timedelta(minutes=i), interval_seconds=60, energy_kwh=1)
            for i in range(501)])
        response = self.client.get(self.url, {'page_size': 100000})
        self.assertEqual(response.data['count'], 501)
        self.assertEqual(len(response.data['results']), 500)
        self.assertIsNotNone(response.data['next'])
        self.assertEqual(len(self.client.get(self.url).data['results']), 100)


class InventoryConcurrencyAPITests(TransactionTestCase):
    """Dispatch DRF views on separate connections, preserving session timeouts."""

    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        User = get_user_model()
        self.user = User.objects.create_user(username='concur_user', password='password123')
        self.building = Building.objects.create(name='Concurrent lab', has_solar_installation=True)
        self.other = Building.objects.create(name='Other lab', has_solar_installation=False)
        self.minute = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)

    def request(self, method, url, data):
        # APIRequestFactory avoids request middleware closing the connection on
        # which this worker just installed bounded PostgreSQL timeouts.
        request = APIRequestFactory().generic(method, url, json.dumps(data), content_type='application/json')
        force_authenticate(request, user=self.user)
        route = resolve(url)
        return route.func(request, **route.kwargs)

    def worker(self, operation, barrier=None):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
                cursor.execute("SET statement_timeout = '8s'")
                cursor.execute('SELECT pg_backend_pid()')
                pid = cursor.fetchone()[0]
            if barrier is not None:
                barrier.wait(timeout=10)
            if operation[0] == 'generate':
                return pid, generate_minute(self.minute, now=self.minute + timedelta(minutes=1))
            response = self.request(*operation)
            return pid, response.status_code, response.data
        finally:
            connections['default'].close()

    def race(self, first, second):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(self.worker, operation, barrier) for operation in [first, second]]
            results = [job.result(timeout=15) for job in jobs]
        self.assertNotEqual(results[0][0], results[1][0])
        return results

    def test_concurrent_active_main_creation_has_one_winner(self):
        url = reverse('building-meter-list', args=[self.building.pk])
        results = self.race(('POST', url, {'device_id': 'MAIN-A'}), ('POST', url, {'device_id': 'MAIN-B'}))
        self.assertCountEqual([r[1] for r in results], [201, 400])
        self.assertEqual(self.building.meters.filter(meter_type='ELECTRICITY', is_active=True).count(), 1)

    def test_concurrent_main_activation_has_one_winner(self):
        a = Meter.objects.create(building=self.building, device_id='MAIN-A', is_active=False)
        b = Meter.objects.create(building=self.building, device_id='MAIN-B', is_active=False)
        results = self.race(('PATCH', reverse('meter-detail', args=[a.pk]), {'is_active': True}),
                            ('PATCH', reverse('meter-detail', args=[b.pk]), {'is_active': True}))
        self.assertCountEqual([r[1] for r in results], [200, 400])
        self.assertEqual(self.building.meters.filter(is_active=True).count(), 1)

    def test_concurrent_solar_activation_has_one_winner(self):
        a = Meter.objects.create(building=self.building, device_id='PV-A', meter_type='SOLAR', is_active=False)
        b = Meter.objects.create(building=self.building, device_id='PV-B', meter_type='SOLAR', is_active=False)
        results = self.race(('PATCH', reverse('meter-detail', args=[a.pk]), {'is_active': True}),
                            ('PATCH', reverse('meter-detail', args=[b.pk]), {'is_active': True}))
        self.assertCountEqual([r[1] for r in results], [200, 400])
        self.assertEqual(self.building.meters.filter(meter_type='SOLAR', is_active=True).count(), 1)

    def test_solar_creation_and_absence_declaration_cannot_both_win(self):
        results = self.race(('POST', reverse('building-meter-list', args=[self.building.pk]),
                             {'device_id': 'PV', 'meter_type': 'SOLAR'}),
                            ('PATCH', reverse('building-detail', args=[self.building.pk]),
                             {'has_solar_installation': False}))
        self.assertEqual(sum(r[1] in (200, 201) for r in results), 1)
        self.assertEqual(sum(r[1] == 400 for r in results), 1)
        self.building.refresh_from_db()
        self.assertEqual(self.building.has_solar_installation, self.building.meters.filter(meter_type='SOLAR').exists())

    def test_duplicate_device_id_race_across_buildings_is_field_error(self):
        url_a = reverse('building-meter-list', args=[self.building.pk])
        url_b = reverse('building-meter-list', args=[self.other.pk])
        inserted = False

        def inject(execute, sql, params, many, context):
            nonlocal inserted
            if not inserted and sql.startswith('INSERT INTO "monitoring_meter"'):
                inserted = True
                with ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(self.worker, ('POST', url_b, {'device_id': 'GLOBAL-ID'}))
                    self.assertEqual(result.result(timeout=15)[1], 201)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(inject):
            response = self.request('POST', url_a, {'device_id': 'GLOBAL-ID'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('device_id', response.data)
        self.assertEqual(Meter.objects.get(device_id='GLOBAL-ID').building_id, self.other.pk)
        self.assertFalse(self.building.meters.exists())

    def test_generator_and_api_deactivation_use_compatible_lock_order(self):
        # A no-solar building with old eligible meters lets either ordering win.
        meters = [Meter.objects.create(building=self.other, device_id=kind, meter_type=kind)
                  for kind in ['ELECTRICITY', 'HVAC', 'LIGHTING']]
        self.other.meters.update(created_at=self.minute - timedelta(days=1))
        results = self.race(('generate',),
                            ('PATCH', reverse('meter-detail', args=[meters[0].pk]), {'is_active': False}))
        self.assertEqual(results[1][1], 200)
        meters[0].refresh_from_db()
        self.assertFalse(meters[0].is_active)
        count = EnergyReading.objects.filter(meter__building=self.other).count()
        self.assertIn(count, [0, 3])  # Whole set committed first, or generation paused.
        self.assertEqual(results[0][1]['failed'], 0)
