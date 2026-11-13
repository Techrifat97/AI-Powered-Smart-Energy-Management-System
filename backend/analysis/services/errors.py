"""Exception hierarchy for the analysis (S3) services."""


class AnalysisError(Exception):
    """Base class for expected, reportable S3 failures."""


class ReportUnavailable(AnalysisError):
    """A cost report cannot be produced; `reason` is a stable machine-readable code."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class ExplanationUnavailable(AnalysisError):
    """One cost explainer could not produce a text; the next explainer is tried."""
