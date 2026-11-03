from .processor import StreamProcessor


class MeterFilter(StreamProcessor):
    """
    Concrete StreamProcessor that filters meter reading events based on:
      1. Meter activity status (`is_active` flag)
      2. Power threshold (`power_kw` >= min_power_kw)
      3. Optional category matching (`category` in allowed_categories)

    Follows the shared technical rules:
      - Uses `None` to indicate filtered-out events.
      - Returns a valid event dictionary if it passes all criteria.
    """

    def __init__(self, min_power_kw=0.0, filter_inactive=True, allowed_categories=None):
        self.min_power_kw = 0.0
        self.filter_inactive = True
        self.allowed_categories = None

        self.set_min_power_kw(min_power_kw)
        self.set_filter_inactive(filter_inactive)
        if allowed_categories is not None:
            self.set_allowed_categories(allowed_categories)

    # --- Getters & Setters ---
    def get_min_power_kw(self):
        return self.min_power_kw

    def set_min_power_kw(self, min_power_kw):
        if not isinstance(min_power_kw, (int, float)):
            raise TypeError("min_power_kw must be a numeric value")
        if min_power_kw < 0:
            raise ValueError("min_power_kw cannot be negative")
        self.min_power_kw = float(min_power_kw)

    def get_filter_inactive(self):
        return self.filter_inactive

    def set_filter_inactive(self, filter_inactive):
        self.filter_inactive = bool(filter_inactive)

    def get_allowed_categories(self):
        return set(self.allowed_categories) if self.allowed_categories is not None else None

    def set_allowed_categories(self, categories):
        if categories is None:
            self.allowed_categories = None
        else:
            self.allowed_categories = {str(c).strip().upper() for c in categories}

    # --- Core Processing Logic ---
    def process(self, event: dict) -> dict | None:
        """
        Filters an incoming event dictionary.

        Returns:
            dict: The original event dictionary if it passes all filters.
            None: If the event is inactive, below power threshold, or filtered by category.
        """
        if not isinstance(event, dict):
            return None

        # 1. Filter out inactive meters
        if self.filter_inactive and not event.get("is_active", True):
            return None

        # 2. Filter readings below the configured power threshold
        power_kw = event.get("power_kw")
        if power_kw is not None and power_kw < self.min_power_kw:
            return None

        # 3. Filter by category if allowed_categories is configured
        if self.allowed_categories is not None:
            event_category = str(event.get("category", "")).strip().upper()
            if event_category not in self.allowed_categories:
                return None

        # Return a copy to ensure immutability and prevent unexpected in-place mutations
        return dict(event)
