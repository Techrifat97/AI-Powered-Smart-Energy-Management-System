"""Explicit demo setup preserves compatible data and refuses incompatible sets."""

from io import StringIO

from django.core.management import call_command, CommandError
from django.test import TestCase

from monitoring.models import Building, Meter


class DemoInventoryTests(TestCase):
    def setup_demo(self):
        call_command('setup_demo_inventory', stdout=StringIO())

    def test_creates_supported_four_meter_inventory_without_readings(self):
        self.setup_demo()
        building = Building.objects.get(name='Campus Sonnenstraße Dortmund')
        self.assertIs(building.has_solar_installation, True)
        self.assertEqual(building.meters.count(), 4)
        self.assertCountEqual(building.meters.values_list('meter_type', flat=True),
                              ['ELECTRICITY', 'HVAC', 'LIGHTING', 'SOLAR'])
        self.assertFalse(building.meters.filter(is_active=False).exists())
        self.assertFalse(building.meters.exclude(unit='kWh').exists())
        for meter in building.meters.all():
            self.assertFalse(meter.readings.exists())

    def test_repeat_preserves_all_existing_inventory_fields(self):
        self.setup_demo()
        before_buildings = list(Building.objects.values())
        before_meters = list(Meter.objects.order_by('pk').values())
        self.setup_demo()
        self.assertEqual(list(Building.objects.values()), before_buildings)
        self.assertEqual(list(Meter.objects.order_by('pk').values()), before_meters)

    def test_rejects_incompatible_metadata_without_modification(self):
        building = Building.objects.create(name='Campus Sonnenstraße Dortmund', has_solar_installation=False)
        with self.assertRaisesRegex(CommandError, 'incompatible'):
            self.setup_demo()
        building.refresh_from_db()
        self.assertFalse(building.has_solar_installation)
        self.assertFalse(Meter.objects.exists())

    def test_rejects_inactive_meter_and_preserves_status(self):
        self.setup_demo()
        Meter.objects.filter(meter_type='HVAC').update(is_active=False)
        before = list(Meter.objects.order_by('pk').values())
        with self.assertRaisesRegex(CommandError, 'incompatible'):
            self.setup_demo()
        self.assertEqual(list(Meter.objects.order_by('pk').values()), before)

    def test_reserved_device_id_collision_does_not_leave_partial_building(self):
        other = Building.objects.create(name='Other')
        meter = Meter.objects.create(building=other, device_id='DO-SON-MAIN')
        with self.assertRaisesRegex(CommandError, 'assigned elsewhere'):
            self.setup_demo()
        self.assertEqual(Building.objects.count(), 1)
        self.assertEqual(Meter.objects.get().pk, meter.pk)

    def test_partial_existing_inventory_is_not_silently_completed(self):
        building = Building.objects.create(name='Campus Sonnenstraße Dortmund', has_solar_installation=True)
        Meter.objects.create(building=building, device_id='DO-SON-MAIN')
        with self.assertRaisesRegex(CommandError, 'incompatible'):
            self.setup_demo()
        self.assertEqual(building.meters.count(), 1)

    def test_ambiguous_demo_name_is_rejected(self):
        for _ in range(2):
            Building.objects.create(name='Campus Sonnenstraße Dortmund', has_solar_installation=True)
        with self.assertRaisesRegex(CommandError, 'Multiple'):
            self.setup_demo()
        self.assertEqual(Building.objects.count(), 2)
        self.assertFalse(Meter.objects.exists())
