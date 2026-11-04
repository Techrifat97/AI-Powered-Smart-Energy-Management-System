"""Run a short terminal demonstration with configurable cycles and delays."""

import argparse
import random

from .processors import EnergyTransformer, MeterFilter, PeakTariffProcessor
from .source import MeterReadingStream, TelemetryGenerator


def count_events(events, counts):
    """Count incoming events while leaving the stream lazy."""
    for event in events:
        counts["generated"] += 1
        yield event


def print_event(event):
    status = "PEAK" if event["is_peak"] else "ACCEPTED"
    mode = event.get("battery_mode", "-")
    print(
        f'[{event["timestamp"][11:19]} UTC] meter={event["meter_id"]} '
        f'{event["category"]:7} {mode:11} {event["power_kw"]:4.2f} kW '
        f'energy={event["consumption_kwh"]:.6f} kWh '
        f'net contribution={event["net_grid_contribution_kwh"]:+.6f} kWh {status}',
        flush=True
    )


def main():
    parser = argparse.ArgumentParser(description="Hometask 2 energy streaming demonstration")
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--interval", type=float, default=1, help="Seconds to wait between cycles")
    parser.add_argument("--measurement-seconds", type=float, default=60,
                        help="Duration represented by each measurement")
    parser.add_argument("--min-power-kw", type=float, default=0.5)
    parser.add_argument("--peak-threshold-kw", type=float, default=4.0)
    parser.add_argument("--seed", type=int, default=None, help="Repeatable simulated power values")
    args = parser.parse_args()

    meters = [
        {"meter_id": 1, "category": "HVAC", "is_active": True},
        {"meter_id": 2, "category": "SOLAR", "is_active": True},
        {"meter_id": 3, "category": "BATTERY", "is_active": True, "battery_mode": "CHARGING"},
        {"meter_id": 4, "category": "BATTERY", "is_active": True, "battery_mode": "DISCHARGING"},
        {"meter_id": 5, "category": "HVAC", "is_active": False}
    ]
    if args.seed is not None:
        random.seed(args.seed)

    try:
        generator = TelemetryGenerator(meters, measurement_seconds=args.measurement_seconds)
        pipeline = (
            MeterFilter(min_power_kw=args.min_power_kw)
            | EnergyTransformer()
            | PeakTariffProcessor(threshold_kw=args.peak_threshold_kw)
        )
        counts = {"generated": 0}
        readings = generator.generate(cycles=args.cycles, interval=args.interval)
        stream = MeterReadingStream(count_events(readings, counts))
        print(f"Measurement: {args.measurement_seconds:g}s; wait between cycles: {args.interval:g}s",
              flush=True)
        accepted = 0
        for event in pipeline.run(stream):
            print_event(event)
            accepted += 1
        filtered = counts["generated"] - accepted
        print(f'Generated {counts["generated"]}; accepted {accepted}; filtered {filtered}.', flush=True)
    except (TypeError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
