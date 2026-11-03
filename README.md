# AI-Powered Smart Energy Management System

**Group 25**

**Hometask 2 — Real-Time Data Processing**

This is our Capstone project for the Compact Programming course at FH Dortmund. Our goal is to monitor energy use in buildings and process smart-meter data for analysis and sustainability recommendations.

For Hometask 2, we are building one shared streaming framework in Python. It will simulate incoming readings from HVAC, solar and battery meters, filter out readings we do not need, and transform the remaining data into useful energy information.

## Team Members and Responsibilities

| Member | Student ID | Program | Classes | Responsibility | Progress |
|---|---|---|---|---|---|
| Rifat Ali Shaon | 7225871 | MDT | `MeterReadingStream`, `TelemetryGenerator` | Generate meter readings and consume them using iterators and generators | Implemented |
| Syed Yasoob Raza | 7226703 | ESE | `StreamProcessor`, `MeterFilter` | Define an abstract processing interface and filter inactive or low-power readings | In progress |
| Marwan Ahmed | 7226233 | MDT | `EnergyTransformer`, `PeakTariffProcessor`, `StreamPipeline` | Transform readings and connect the processing stages into one pipeline | In progress |

The classes will work together as a single pipeline, rather than as three separate applications.

## How Our Streaming Pipeline Works

Our planned data flow is:

```text
Smart meter events (HVAC / SOLAR / BATTERY)
        |
        v
TelemetryGenerator
        |
        v
MeterReadingStream
        |
        v
MeterFilter
        |
        v
EnergyTransformer
        |
        v
PeakTariffProcessor
        |
        v
Processed energy events
```

The source part is implemented. The filter, transformations and full pipeline will be connected after the other components are ready.

We are using the following Python concepts in this assignment:

- **Abstract Base Classes:** a common `StreamProcessor` interface using `ABC` and `@abstractmethod`
- **Inheritance and polymorphism:** different processors with the same `process(event)` method
- **Operator overloading:** using `__or__()` to connect processing stages
- **Iterators:** using `__iter__()` and `__next__()` to consume events one at a time
- **Generators:** using `yield` to produce simulated readings

## Shared Event Format

The streaming components use Python dictionaries. A generated reading looks like this:

```python
{
    "meter_id": 1,
    "category": "HVAC",
    "is_active": True,
    "power_kw": 2.5,
    "consumption_kwh": 1.2,
    "timestamp": "2026-11-02T21:58:16+00:00"
}
```

The generator produces readings for both active and inactive meters. Filtering happens later in the pipeline. We use `power_kw` for threshold filtering and `consumption_kwh` for energy-related calculations.

## Current Implementation

### MeterReadingStream

This class takes a list or generator of events and returns them one at a time. It implements `__iter__()` and `__next__()`.

### TelemetryGenerator

This class uses `yield` to generate simulated readings. We can set the number of cycles and the time interval between cycles.

Our current demo uses **10 meters and 5 cycles**, so it generates **50 events**. The simulation waits one second between cycles. It does not connect to physical IoT devices yet.

## Project Structure

The Hometask 2 source files currently available are:

```text
backend/
    streaming/
        __init__.py
        source.py
        tests/
            test_source.py
```

The repository also contains the domain classes from Hometask 1. Additional streaming processor files will be added as the team completes them.

## Run the Demo

From the project root, run:

```bash
python3 -m backend.streaming.source
```

This prints the simulated meter events as they are generated.

## Run the Tests

We use Python's built-in `unittest` framework.

```bash
python3 -m unittest discover -s backend/streaming/tests -v
```

The current source implementation has **5 passing tests** covering normal iteration, empty streams, event generation, multiple cycles and 50 generated events. We will add more tests when the other processing components are integrated.

## UML Class Diagram

The final streaming UML class diagram will be added here after the shared processor interfaces and class relationships are verified against the completed code.

## Team Video Presentation

**Video link:** To be added before submission.

## Remaining Work

We still need to integrate the meter filter, energy transformations and pipeline composition; test the complete event flow; add the final UML class diagram; and include our five-minute team presentation link.
