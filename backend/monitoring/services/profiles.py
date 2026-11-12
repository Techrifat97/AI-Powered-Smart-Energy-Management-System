"""Composable deterministic synthetic profiles. Internal power is integer watts."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from math import isfinite
from types import MappingProxyType


@dataclass(frozen=True)
class EnergyQuantity:
    """Interval energy in kWh; addition accepts energy quantities only."""
    kwh: float

    def __post_init__(self):
        if isinstance(self.kwh, bool) or not isinstance(self.kwh, (int, float)) or not isfinite(self.kwh) or self.kwh < 0:
            raise ValueError('Energy must be finite and nonnegative.')

    def __add__(self, other):
        if not isinstance(other, EnergyQuantity):
            return NotImplemented
        return EnergyQuantity(self.kwh + other.kwh)


@dataclass(frozen=True)
class ProfileContext:
    building_id: int
    timestamp: datetime
    fingerprint: str
    hvac_count: int
    lighting_count: int
    main_watts: int = 0


class EnergyProfile(ABC):
    @abstractmethod
    def calculate_power(self, context: ProfileContext) -> int:
        """Return nonnegative integer watts, not interval energy."""


class ElectricityProfile(EnergyProfile):
    def calculate_power(self, context: ProfileContext) -> int:
        minute = context.timestamp
        seed = f's1-synthetic-v1|{context.building_id}|{minute.isoformat()}|{context.fingerprint}'
        variation = int.from_bytes(sha256(seed.encode()).digest()[:4], 'big') % 1000
        base = (8000 if minute.weekday() >= 5 else 12000) if 8 <= minute.hour < 18 else 4000
        return base + variation


class HVACProfile(EnergyProfile):
    def calculate_power(self, context: ProfileContext) -> int:
        return (context.main_watts * 30 // 100) // context.hvac_count


class LightingProfile(EnergyProfile):
    def calculate_power(self, context: ProfileContext) -> int:
        return (context.main_watts * 15 // 100) // context.lighting_count


class SolarProfile(EnergyProfile):
    def calculate_power(self, context: ProfileContext) -> int:
        minute = context.timestamp
        return 10000 * max(0, 360 - abs(minute.hour * 60 + minute.minute - 720)) // 360


class TelemetryGenerator:
    """Compose polymorphic strategies; never retain ORM inventory between cycles."""
    def __init__(self, profiles=None):
        self._profiles = MappingProxyType(dict(profiles or {
            'ELECTRICITY': ElectricityProfile(), 'HVAC': HVACProfile(),
            'LIGHTING': LightingProfile(), 'SOLAR': SolarProfile()}))

    def iter_readings(self, building, meters, timestamp, *, interval_seconds=60):
        """Yield one measurement at a time. History explicitly supplies 3600 seconds."""
        meters = tuple(meters)
        context = ProfileContext(building.pk, timestamp,
            ','.join(f'{m.pk}:{m.meter_type}:{m.device_id}' for m in meters),
            sum(m.meter_type == 'HVAC' for m in meters),
            sum(m.meter_type == 'LIGHTING' for m in meters))
        context = replace(context, main_watts=self._profiles['ELECTRICITY'].calculate_power(context))
        included = EnergyQuantity(0)
        gross = EnergyQuantity(context.main_watts / 1000 * interval_seconds / 3600)
        for meter in meters:
            watts = self._profiles[meter.meter_type].calculate_power(context)
            power = watts / 1000
            # Preserve v1's exact floating point operation for live retries.
            energy = EnergyQuantity(power / 60 if interval_seconds == 60 else power * interval_seconds / 3600)
            if meter.meter_type in ('HVAC', 'LIGHTING'):
                included = included + energy
                if included.kwh > gross.kwh:
                    raise ValueError('Included submeter allocation exceeds gross load.')
            yield dict(meter=meter, timestamp=timestamp, interval_seconds=interval_seconds,
                       energy_kwh=energy.kwh, power_kw=power, voltage=230.0)
