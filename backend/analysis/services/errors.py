"""Exception hierarchy for the analysis (S3) services."""


class AnalysisError(Exception):
    """Base class for expected, reportable S3 failures."""


class ReportUnavailable(AnalysisError):
    """A cost report cannot be produced; `reason` is a stable machine-readable code."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason
