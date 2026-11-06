"""Error handling for the S1 Monitoring & Analytics subsystem."""

import logging

logger = logging.getLogger(__name__)


class MonitoringError(Exception):
    """Base class for every error raised by the monitoring subsystem."""

    code = "MONITORING_ERROR"


class MonitoringValueError(MonitoringError, ValueError):
    """A value is out of range or malformed. Still catchable as ValueError."""

    code = "MONITORING_VALUE_ERROR"


class MonitoringTypeError(MonitoringError, TypeError):
    """A value has the wrong type. Still catchable as TypeError."""

    code = "MONITORING_TYPE_ERROR"


class InvalidReadingError(MonitoringValueError):
    code = "INVALID_READING"


class InvalidMeterError(MonitoringValueError):
    code = "INVALID_METER"


class InvalidBuildingError(MonitoringValueError):
    code = "INVALID_BUILDING"


class InvalidEventError(MonitoringValueError):
    code = "INVALID_EVENT"


class InvalidSummaryError(MonitoringValueError):
    code = "INVALID_SUMMARY"


class MonitoringErrorHandler:
    """Runs an operation and turns any failure into a safe, structured result."""

    def handle(self, error):
        """Convert an exception into a result dict and log it."""
        if isinstance(error, MonitoringError):
            code = error.code
        else:
            code = "UNEXPECTED_ERROR"
        logger.warning("%s: %s", code, error)
        return {"ok": False, "code": code, "error": str(error)}

    def safe_call(self, func, *args, **kwargs):
        """Call func; return {"ok": True, "value": ...} or the handled error."""
        try:
            return {"ok": True, "value": func(*args, **kwargs)}
        except Exception as error:
            return self.handle(error)
