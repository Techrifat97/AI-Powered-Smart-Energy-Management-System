class UserPreferences:
    THEMES = ("LIGHT", "DARK")
    DEFAULT_UNIT = "kWh"
    DEFAULT_THEME = "LIGHT"
    DEFAULT_THRESHOLD_KW = 100.0

    def __init__(self, display_unit=None, theme=None,
                 default_building_id=None, alert_threshold_kw=None):
        self.display_unit = None
        self.theme = None
        self.default_building_id = None
        self.alert_threshold_kw = None
        self.reset()
        if display_unit is not None:
            self.set_display_unit(display_unit)
        if theme is not None:
            self.set_theme(theme)
        if default_building_id is not None:
            self.set_default_building_id(default_building_id)
        if alert_threshold_kw is not None:
            self.set_alert_threshold_kw(alert_threshold_kw)

    def get_display_unit(self):
        return self.display_unit

    def get_theme(self):
        return self.theme

    def get_default_building_id(self):
        return self.default_building_id

    def get_alert_threshold_kw(self):
        return self.alert_threshold_kw

    def set_display_unit(self, new_unit):
        if not new_unit:
            raise ValueError("Display unit cannot be empty")
        self.display_unit = new_unit

    def set_theme(self, new_theme):
        if new_theme not in UserPreferences.THEMES:
            raise ValueError("Theme must be LIGHT or DARK")
        self.theme = new_theme

    def set_default_building_id(self, building_id):
        self.default_building_id = building_id

    def set_alert_threshold_kw(self, threshold_kw):
        if threshold_kw <= 0:
            raise ValueError("Alert threshold must be positive")
        self.alert_threshold_kw = float(threshold_kw)

    def reset(self):
        self.display_unit = UserPreferences.DEFAULT_UNIT
        self.theme = UserPreferences.DEFAULT_THEME
        self.default_building_id = None
        self.alert_threshold_kw = UserPreferences.DEFAULT_THRESHOLD_KW
