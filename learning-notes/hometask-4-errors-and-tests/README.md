# AI-Powered Smart Energy Management System

Group 25 | Compact Programming | FH Dortmund

# Hometask 4: Exception Handling and Unit Tests

## 1. About the Hometask

Our Capstone project is an AI-Powered Smart Energy Management System. For Hometask 4, we focused on **error handling** and **automated testing** in Python.

The assignment asks for two things:

1. An error-handling class for each subsystem.
2. At least 15 different tests.

Before this hometask, our code raised plain `ValueError` and `TypeError` exceptions. A caller could not tell which problem had happened or which subsystem it came from. We replaced them with custom exceptions and added one error-handling class per subsystem.

This assignment is implemented in plain Python. It needs no database, web interface or external library.

| Requirement | Our answer |
|---|---|
| Error-handling class per subsystem | `MonitoringErrorHandler` (S1), `CoachErrorHandler` (S2), `DecisionsErrorHandler` (S3) |
| 15 different tests | 23 new tests in three `test_errors.py` files |
| GitHub link | Branch `Homeworkassignment-04` |

## 2. Team Members

| Name | Student ID | Programme | Subsystem |
|---|---|---|---|
| Rifat Ali Shaon | 7225871 | MDT | S1: Energy Monitoring & Data Management |
| Syed Yasoob Raza | 7226703 | ESE | S2: Sustainability & AI Coach |
| Marwan Ahmed | 7226233 | MDT | S3: Cost, Scenarios & Alerts |

## 3. Python Concepts Used

| Concept | Implementation |
|---|---|
| Custom exceptions | Each subsystem defines its own exception classes, such as `InvalidMeterError` and `InvalidTariffError`. |
| Inheritance | All errors of a subsystem inherit from one base class (`MonitoringError`, `CoachError`, `DecisionsError`). |
| Multiple inheritance | S1 and S2 combine their base class with a built-in one, for example `MonitoringValueError(MonitoringError, ValueError)`. |
| `try / except` | `safe_call()` catches errors and turns them into a result dictionary. |
| Unit testing | `unittest.TestCase`, `setUp`, `assertRaises`, `assertEqual`, `assertTrue`, `assertIsInstance`. |

## 4. Main Classes

Each subsystem has an `errors.py` file with a base exception, specific exceptions and one handler class.

| Subsystem | Module | Base exception | Specific exceptions | Handler |
|---|---|---|---|---|
| S1 Monitoring | `backend/monitoring/errors.py` | `MonitoringError` | `InvalidReadingError`, `InvalidMeterError`, `InvalidBuildingError`, `InvalidEventError`, `InvalidSummaryError` | `MonitoringErrorHandler` |
| S2 Coach | `backend/coach/errors.py` | `CoachError` | `InvalidRecommendationError`, `InvalidFeedbackError`, `InvalidLLMLogError` | `CoachErrorHandler` |
| S3 Decisions | `backend/decisions/errors.py` | `DecisionsError` | `InvalidTariffError`, `InvalidBudgetError`, `InvalidNotificationError`, `InvalidEnergyValueError`, `InvalidScenarioError`, `InvalidThresholdError` | `DecisionsErrorHandler` |

S1 and S2 also have `MonitoringValueError` / `MonitoringTypeError` and `CoachValueError` / `CoachTypeError`. They are used for wrong-type problems and as parents of the specific errors.

Every exception has a short `code` string, such as `INVALID_METER` or `INVALID_TARIFF`, that a program or log can read.

## 5. How Error Handling Works

### The exception hierarchy

The S3 hierarchy:

```
ValueError
   └── DecisionsError                 <- catches any S3 problem
          ├── InvalidTariffError
          ├── InvalidBudgetError
          ├── InvalidNotificationError
          ├── InvalidEnergyValueError
          ├── InvalidScenarioError
          └── InvalidThresholdError
```

- `except DecisionsError` catches any S3 problem, and nothing from S1 or S2.
- `except InvalidTariffError` catches only that one problem.
- The errors still inherit from `ValueError` or `TypeError`, so older code and tests that catch those keep working.

### Raising the new exceptions

We replaced the plain raises. The message stays the same and only the type is more precise:

```python
# before
raise ValueError("Price per kWh must be positive")
# after
raise InvalidTariffError("Price per kWh must be positive")
```

This was done in 17 source files across S1, S2 and S3.

### The error-handling class

```python
class DecisionsErrorHandler:
    def handle(self, error):
        if isinstance(error, DecisionsError):
            code = error.code
        else:
            code = "UNEXPECTED_ERROR"
        logger.warning("%s: %s", code, error)
        return {"ok": False, "code": code, "error": str(error)}

    def safe_call(self, func, *args, **kwargs):
        try:
            return {"ok": True, "value": func(*args, **kwargs)}
        except Exception as error:
            return self.handle(error)
```

- `handle(error)` turns an exception into a dictionary and writes a log line. Unknown exceptions get the code `UNEXPECTED_ERROR`.
- `safe_call(func, ...)` runs a function and never crashes. It returns `{"ok": True, "value": ...}` on success and the handled error dictionary on failure.

Example:

```python
handler = DecisionsErrorHandler()
handler.safe_call(EnergyBudget, 1, 1200)
# {'ok': True, 'value': <EnergyBudget ...>}

handler.safe_call(EnergyBudget, 1, 0)
# {'ok': False, 'code': 'INVALID_BUDGET', 'error': 'Monthly limit must be positive'}
```

`safe_call` catches `Exception` but not `BaseException`, so Ctrl+C and `SystemExit` still stop the program.

## 6. Project Structure

```
AI-Powered-Smart-Energy-Management-System/
|
|-- backend/
|   |-- monitoring/
|   |   |-- errors.py
|   |   |-- tests/
|   |       |-- test_errors.py
|   |-- coach/
|   |   |-- errors.py
|   |   |-- tests/
|   |       |-- test_errors.py
|   |-- decisions/
|       |-- errors.py
|       |-- tests/
|           |-- test_errors.py
|
|-- README.md
```

Only the files added for this hometask are shown. The domain and service classes were edited to raise the new exceptions.

## 7. Unit Testing

We used Python's built-in `unittest` framework. We added 23 tests, which is more than the 15 required, because each subsystem has several exception types to cover.

| Subsystem | File | Tests |
|---|---|---|
| S1 | `backend/monitoring/tests/test_errors.py` | 7 |
| S2 | `backend/coach/tests/test_errors.py` | 6 |
| S3 | `backend/decisions/tests/test_errors.py` | 10 |

The tests fall into three kinds:

1. **Hierarchy tests** check that the new exceptions inherit correctly.
2. **Raising tests** check that bad input raises exactly the right exception.
3. **Handler tests** check that `safe_call` returns the right dictionary for success, a known error and an unexpected error.

The S3 tests:

| Test | Checks |
|---|---|
| hierarchy keeps `ValueError` compatibility | inheritance |
| zero price raises `InvalidTariffError` | tariff validation |
| negative cost raises `InvalidBudgetError` | budget validation |
| unknown severity raises `InvalidNotificationError` | notification validation |
| negative energy raises `InvalidEnergyValueError` | calculator validation |
| reduction over 100% raises `InvalidScenarioError` | simulator validation |
| zero threshold raises `InvalidThresholdError` | detector validation |
| `safe_call` success | `ok` is `True` |
| `safe_call` known error | `code` is `INVALID_BUDGET` |
| `safe_call` unexpected error | `code` is `UNEXPECTED_ERROR` |

Example:

```python
def test_negative_cost_raises_invalid_budget(self):
    with self.assertRaises(InvalidBudgetError):
        EnergyBudget(1, 100).add_cost(-1)
```

The tests are plain `unittest`. Django's test runner also understands them, because `django.test.TestCase` is built on `unittest.TestCase`. They test domain classes directly, so they need no database.

## 8. Running the Tests

The project uses Python 3.9 or later. Run these commands from the project root:

```
python -m unittest discover -s backend/monitoring/tests -t .
python -m unittest discover -s backend/coach/tests -t .
python -m unittest discover -s backend/decisions/tests -t .
```

Test results:

| Subsystem | Tests passed | Tests failed |
|---|---|---|
| S1 Monitoring | 78 | 0 |
| S2 Coach | 20 | 0 |
| S3 Decisions | 20 | 0 |

These totals include the earlier tests, so the existing tests kept passing without changes.

To run only the error tests of one subsystem:

```
python -m unittest backend.decisions.tests.test_errors -v
```

## 9. Conclusion

Each subsystem now has its own exception hierarchy and a handler class that returns one predictable result format for every failure.

Known limitations:

- The handler code is repeated in the three `errors.py` files. `manage.py` and the unittest command resolve imports differently, so each subsystem keeps its own copy.
- The new tests focus on failure paths. The success paths are covered by the earlier tests.
- A non-numeric string passed to the cost estimator fails inside Python's `decimal` module. This is not yet wrapped in a custom exception, so the handler labels it `UNEXPECTED_ERROR`.
- The streaming package from Hometask 2 still uses plain `ValueError` and `TypeError`.
