"""Error handling for the S2 Forecasting & AI Coach subsystem."""

import logging

logger = logging.getLogger(__name__)


class CoachError(Exception):
    """Base class for every error raised by the coach subsystem."""

    code = "COACH_ERROR"


class CoachValueError(CoachError, ValueError):
    """A value is out of range or malformed. Still catchable as ValueError."""

    code = "COACH_VALUE_ERROR"


class CoachTypeError(CoachError, TypeError):
    """A value has the wrong type. Still catchable as TypeError."""

    code = "COACH_TYPE_ERROR"


class InvalidRecommendationError(CoachValueError):
    code = "INVALID_RECOMMENDATION"


class InvalidFeedbackError(CoachValueError):
    code = "INVALID_FEEDBACK"


class InvalidLLMLogError(CoachValueError):
    code = "INVALID_LLM_LOG"


class CoachErrorHandler:
    """Runs an operation and turns any failure into a safe, structured result."""

    def handle(self, error):
        """Convert an exception into a result dict and log it."""
        if isinstance(error, CoachError):
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
