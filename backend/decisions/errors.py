"""Error handling for the S3 Cost, Scenarios & Alerts subsystem."""

import logging

logger = logging.getLogger(__name__)


class DecisionsError(ValueError):
    """Base class for every error raised by the decisions subsystem.

    Inherits from ValueError so code and tests that expect ValueError keep working.
    """

    code = "DECISIONS_ERROR"


class InvalidTariffError(DecisionsError):
    code = "INVALID_TARIFF"


class InvalidBudgetError(DecisionsError):
    code = "INVALID_BUDGET"


class InvalidNotificationError(DecisionsError):
    code = "INVALID_NOTIFICATION"


class InvalidEnergyValueError(DecisionsError):
    code = "INVALID_ENERGY_VALUE"


class InvalidScenarioError(DecisionsError):
    code = "INVALID_SCENARIO"


class InvalidThresholdError(DecisionsError):
    code = "INVALID_THRESHOLD"


class DecisionsErrorHandler:
    """Runs an operation and turns any failure into a safe, structured result."""

    def handle(self, error):
        """Convert an exception into a result dict and log it."""
        if isinstance(error, DecisionsError):
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
