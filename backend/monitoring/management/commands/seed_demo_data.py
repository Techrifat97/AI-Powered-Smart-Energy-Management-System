import math
from datetime import datetime, timedelta, timezone as datetime_timezone
from django.core.management.base import BaseCommand
from django.utils import timezone
from monitoring.models import Building, Meter, EnergyReading


class Command(BaseCommand):
    help = "Populate realistic sample telemetry data for Hometask 3 API demonstration."

    def handle(self, *args, **options):
        self.stdout.write("Seeding sample data for Smart Energy Management System...")

        # 1. Create or get primary demo building
        building, created = Building.objects.get_or_create(
            name="Campus Science Complex - Block A",
            defaults={
                'location': "North Campus, Group 25 Lab",
                'area_sqm': 3500.0,
                'baseline_kwh_per_day': 320.0,
                'has_solar_installation': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created building: {building.name} (ID: {building.id})"))
        else:
            self.stdout.write(f"Using existing building: {building.name} (ID: {building.id})")

        # 2. Create smart meters
        elec_meter, _ = Meter.objects.get_or_create(
            building=building,
            device_id="MTR-ELEC-001",
            defaults={'meter_type': 'ELECTRICITY', 'unit': 'kWh', 'is_active': True}
        )
        hvac_meter, _ = Meter.objects.get_or_create(
            building=building,
            device_id="MTR-HVAC-001",
            defaults={'meter_type': 'HVAC', 'unit': 'kWh', 'is_active': True}
        )
        solar_meter, _ = Meter.objects.get_or_create(
            building=building,
            device_id="MTR-SOLAR-001",
            defaults={'meter_type': 'SOLAR', 'unit': 'kWh', 'is_active': True}
        )

        # 3. Generate 14 days of hourly readings if not already populated
        existing_count = EnergyReading.objects.filter(meter=elec_meter).count()
        if existing_count > 50:
            self.stdout.write(self.style.WARNING(f"Readings already exist ({existing_count} records). Skipping generation."))
            return

        self.stdout.write("Generating 14 days of hourly readings...")
        now = timezone.now().astimezone(datetime_timezone.utc)
        readings_to_create = []

        # 14 days, 24 hours per day = 336 timestamps
        for day_idx in range(14, 0, -1):
            day_date = (now - timedelta(days=day_idx)).date()
            is_weekend = day_date.weekday() >= 5

            for hour in range(24):
                reading_time = timezone.make_aware(
                    datetime(day_date.year, day_date.month, day_date.day, hour, 0, 0),
                    timezone=datetime_timezone.utc,
                )

                # Diurnal profile: base load + daytime peak
                hour_factor = math.sin((hour - 6) / 18.0 * math.pi) if 6 <= hour <= 22 else 0.0
                hour_factor = max(0.0, hour_factor)

                # Weekday vs Weekend multiplier
                activity_mult = 0.45 if is_weekend else 1.0

                # Gross main electricity, including HVAC, lighting and equipment
                elec_power_kw = round(8.0 + (28.0 * hour_factor * activity_mult), 2)
                elec_kwh = round(elec_power_kw * 1.0, 2)
                readings_to_create.append(
                    EnergyReading(
                        meter=elec_meter,
                        timestamp=reading_time,
                        interval_seconds=3600,
                        energy_kwh=elec_kwh,
                        power_kw=elec_power_kw,
                        voltage=230.0
                    )
                )

                # HVAC power (highest in afternoon)
                hvac_factor = math.sin((hour - 8) / 14.0 * math.pi) if 8 <= hour <= 20 else 0.0
                hvac_factor = max(0.0, hvac_factor)
                hvac_power_kw = round(3.0 + (18.0 * hvac_factor * activity_mult), 2)
                hvac_kwh = round(hvac_power_kw * 1.0, 2)
                readings_to_create.append(
                    EnergyReading(
                        meter=hvac_meter,
                        timestamp=reading_time,
                        interval_seconds=3600,
                        energy_kwh=hvac_kwh,
                        power_kw=hvac_power_kw,
                        voltage=230.0
                    )
                )

                # Solar PV generation (bell curve between 08:00 and 18:00)
                solar_factor = math.sin((hour - 7) / 11.0 * math.pi) if 7 <= hour <= 18 else 0.0
                solar_factor = max(0.0, solar_factor)
                solar_power_kw = round(22.0 * solar_factor, 2)
                solar_kwh = round(solar_power_kw * 1.0, 2)
                # A simulated night-time zero is an explicit observation. Old
                # sparse demo rows are never silently backfilled by this command.
                readings_to_create.append(
                    EnergyReading(
                        meter=solar_meter, timestamp=reading_time, interval_seconds=3600,
                        energy_kwh=solar_kwh, power_kw=solar_power_kw, voltage=230.0,
                    )
                )

        EnergyReading.objects.bulk_create(readings_to_create, batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded {len(readings_to_create)} energy readings across 3 meters."
        ))
        self.stdout.write(self.style.SUCCESS(
            f"Ready for testing! Building ID: {building.id} ({building.name})"
        ))

