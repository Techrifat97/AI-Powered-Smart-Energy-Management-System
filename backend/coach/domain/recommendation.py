from datetime import datetime

from .feedback import RecommendationFeedback
from .llm_log import LLMRequestLog


class AIRecommendation:
    """
    Represents an AI-generated or rule-based sustainability energy recommendation.
    Encapsulates recommendation details, energy savings estimates, status lifecycle,
    associated LLM request logs, and user feedback.
    """

    PRIORITIES = ("LOW", "MEDIUM", "HIGH")
    STATUSES = ("NEW", "ACCEPTED", "DISMISSED", "IMPLEMENTED")

    def __init__(
        self,
        recommendation_id,
        title,
        description,
        category,
        est_saving_kwh=0.0,
        est_saving_pct=0.0,
        priority="MEDIUM",
        status="NEW",
        is_fallback=False,
        llm_log=None,
    ):
        self.id = recommendation_id
        self.title = None
        self.description = None
        self.category = None
        self.est_saving_kwh = 0.0
        self.est_saving_pct = 0.0
        self.priority = None
        self.status = None
        self.is_fallback = False
        self.created_at = datetime.now()
        self.feedbacks = []
        self.llm_log = None

        self.set_title(title)
        self.set_description(description)
        self.set_category(category)
        self.set_est_saving_kwh(est_saving_kwh)
        self.set_est_saving_pct(est_saving_pct)
        self.set_priority(priority)
        self.set_status(status)
        self.set_is_fallback(is_fallback)
        if llm_log is not None:
            self.set_llm_log(llm_log)

    # --- Getters ---
    def get_id(self):
        return self.id

    def get_title(self):
        return self.title

    def get_description(self):
        return self.description

    def get_category(self):
        return self.category

    def get_est_saving_kwh(self):
        return self.est_saving_kwh

    def get_est_saving_pct(self):
        return self.est_saving_pct

    def get_priority(self):
        return self.priority

    def get_status(self):
        return self.status

    def get_is_fallback(self):
        return self.is_fallback

    def get_created_at(self):
        return self.created_at

    def get_feedbacks(self):
        return list(self.feedbacks)

    def get_llm_log(self):
        return self.llm_log

    # --- Setters / Encapsulation ---
    def set_title(self, new_title):
        if not new_title or not isinstance(new_title, str):
            raise ValueError("Title must be a non-empty string")
        self.title = new_title.strip()

    def set_description(self, new_desc):
        if not new_desc or not isinstance(new_desc, str):
            raise ValueError("Description must be a non-empty string")
        self.description = new_desc.strip()

    def set_category(self, new_category):
        if not new_category or not isinstance(new_category, str):
            raise ValueError("Category must be a non-empty string")
        self.category = new_category.strip().upper()

    def set_est_saving_kwh(self, new_saving):
        if not isinstance(new_saving, (int, float)) or new_saving < 0:
            raise ValueError("Estimated saving (kWh) must be a non-negative number")
        self.est_saving_kwh = float(new_saving)

    def set_est_saving_pct(self, new_pct):
        if not isinstance(new_pct, (int, float)) or not (0.0 <= new_pct <= 100.0):
            raise ValueError("Estimated saving percentage must be between 0.0 and 100.0")
        self.est_saving_pct = float(new_pct)

    def set_priority(self, new_priority):
        if not isinstance(new_priority, str):
            raise TypeError("Priority must be a string")
        upper_priority = new_priority.strip().upper()
        if upper_priority not in AIRecommendation.PRIORITIES:
            raise ValueError(f"Priority must be one of: {', '.join(AIRecommendation.PRIORITIES)}")
        self.priority = upper_priority

    def set_status(self, new_status):
        if not isinstance(new_status, str):
            raise TypeError("Status must be a string")
        upper_status = new_status.strip().upper()
        if upper_status not in AIRecommendation.STATUSES:
            raise ValueError(f"Status must be one of: {', '.join(AIRecommendation.STATUSES)}")
        self.status = upper_status

    def set_is_fallback(self, is_fallback):
        self.is_fallback = bool(is_fallback)

    def set_llm_log(self, llm_log):
        if llm_log is not None and not isinstance(llm_log, LLMRequestLog):
            raise TypeError("llm_log must be an instance of LLMRequestLog or None")
        self.llm_log = llm_log

    # --- Domain Methods ---
    def add_feedback(self, feedback):
        """Adds a RecommendationFeedback instance to this recommendation."""
        if not isinstance(feedback, RecommendationFeedback):
            raise TypeError("Feedback must be an instance of RecommendationFeedback")
        self.feedbacks.append(feedback)

    def average_feedback_rating(self):
        """Calculates and returns the average feedback rating, or 0.0 if no feedback exists."""
        if not self.feedbacks:
            return 0.0
        total = sum(fb.get_rating() for fb in self.feedbacks)
        return round(total / len(self.feedbacks), 2)

    def is_actionable(self):
        """Checks if the recommendation is currently pending action."""
        return self.status in ("NEW", "ACCEPTED")

