from datetime import datetime


class LLMRequestLog:
    """
    Tracks and logs LLM model interactions, execution latency,
    token usage, and response statuses for AI recommendations.
    """

    ALLOWED_STATUSES = ("PENDING", "SUCCESS", "FAILED", "TIMEOUT")

    def __init__(self, log_id, model_name, prompt_hash, tokens_used=0, latency_ms=0, status="PENDING"):
        self.id = log_id
        self.model_name = None
        self.prompt_hash = None
        self.tokens_used = 0
        self.latency_ms = 0
        self.status = None
        self.created_at = datetime.now()

        self.set_model_name(model_name)
        self.set_prompt_hash(prompt_hash)
        self.set_tokens_used(tokens_used)
        self.set_latency_ms(latency_ms)
        self.set_status(status)

    # --- Getters ---
    def get_id(self):
        return self.id

    def get_model_name(self):
        return self.model_name

    def get_prompt_hash(self):
        return self.prompt_hash

    def get_tokens_used(self):
        return self.tokens_used

    def get_latency_ms(self):
        return self.latency_ms

    def get_status(self):
        return self.status

    def get_created_at(self):
        return self.created_at

    # --- Setters / Encapsulation ---
    def set_model_name(self, new_model_name):
        if not new_model_name or not isinstance(new_model_name, str):
            raise ValueError("Model name must be a non-empty string")
        self.model_name = new_model_name.strip()

    def set_prompt_hash(self, new_prompt_hash):
        if not new_prompt_hash or not isinstance(new_prompt_hash, str):
            raise ValueError("Prompt hash must be a non-empty string")
        self.prompt_hash = new_prompt_hash.strip()

    def set_tokens_used(self, new_tokens):
        if not isinstance(new_tokens, int) or new_tokens < 0:
            raise ValueError("Tokens used must be a non-negative integer")
        self.tokens_used = new_tokens

    def set_latency_ms(self, new_latency):
        if not isinstance(new_latency, (int, float)) or new_latency < 0:
            raise ValueError("Latency must be a non-negative number")
        self.latency_ms = int(new_latency)

    def set_status(self, new_status):
        if not isinstance(new_status, str):
            raise TypeError("Status must be a string")
        upper_status = new_status.strip().upper()
        if upper_status not in LLMRequestLog.ALLOWED_STATUSES:
            raise ValueError(f"Status must be one of: {', '.join(LLMRequestLog.ALLOWED_STATUSES)}")
        self.status = upper_status

    # --- Domain Methods ---
    def record(self, tokens_used=None, latency_ms=None, status="SUCCESS", **kwargs):
        """
        Records the completion metrics for this LLM request.
        Supports:
          - A dictionary response: record({"tokens_used": 150, "latency_ms": 320, "status": "SUCCESS"})
          - Positional arguments: record(150, 320, "SUCCESS")
          - Keyword arguments: record(tokens_used=150, latency_ms=320, status="SUCCESS")
        """
        response_dict = None
        if isinstance(tokens_used, dict):
            response_dict = tokens_used
        elif "response" in kwargs and isinstance(kwargs["response"], dict):
            response_dict = kwargs["response"]

        if response_dict is not None:
            tokens = response_dict.get("tokens_used", 0)
            latency = response_dict.get("latency_ms", 0)
            resp_status = response_dict.get("status", "SUCCESS")
            self.set_tokens_used(tokens)
            self.set_latency_ms(latency)
            self.set_status(resp_status)
            return

        if tokens_used is not None:
            self.set_tokens_used(tokens_used)
        if latency_ms is not None:
            self.set_latency_ms(latency_ms)
        if status is not None:
            self.set_status(status)
