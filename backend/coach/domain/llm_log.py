from datetime import datetime
from ..errors import CoachTypeError, InvalidLLMLogError


class LLMRequestLog:
    """
    Tracks and logs LLM model interactions, execution latency,
    and success status for AI recommendations.

    Attributes:
        model: str
        latency_ms: int
        success: bool
    """

    def __init__(self, model: str, latency_ms: int = 0, success: bool = True, log_id=None):
        self.id = log_id
        self.model = None
        self.latency_ms = 0
        self.success = True
        self.recorded_at = datetime.now()

        self.set_model(model)
        self.set_latency_ms(latency_ms)
        self.set_success(success)

    # --- Getters ---
    def get_id(self):
        return self.id

    def get_model(self) -> str:
        return self.model

    def get_latency_ms(self) -> int:
        return self.latency_ms

    def get_success(self) -> bool:
        return self.success

    def get_recorded_at(self) -> datetime:
        return self.recorded_at

    # --- Setters / Encapsulation ---
    def set_model(self, new_model: str) -> None:
        if not new_model or not isinstance(new_model, str):
            raise InvalidLLMLogError("Model must be a non-empty string")
        self.model = new_model.strip()

    def set_latency_ms(self, new_latency: int) -> None:
        if not isinstance(new_latency, (int, float)) or new_latency < 0:
            raise InvalidLLMLogError("Latency must be a non-negative number")
        self.latency_ms = int(new_latency)

    def set_success(self, new_success: bool) -> None:
        if not isinstance(new_success, bool):
            raise CoachTypeError("Success must be a boolean")
        self.success = new_success

    # --- Domain Methods ---
    def record(self, latency_ms: int = None, success: bool = None) -> None:
        """
        Records the completion metrics for this LLM request.
        Can be called with no arguments as record() or with updated metrics.
        """
        if latency_ms is not None:
            self.set_latency_ms(latency_ms)
        if success is not None:
            self.set_success(success)
        self.recorded_at = datetime.now()
