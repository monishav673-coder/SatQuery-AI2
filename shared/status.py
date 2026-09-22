"""
SATQUERY AI — Shared status constants
Used by both backend and worker to report honest system status.
"""

class AnalysisStatus:
    CREATED    = "created"
    QUEUED     = "queued"
    PROCESSING = "processing"
    VALIDATING = "validating"
    COMPLETED  = "completed"
    FAILED     = "failed"
    CANCELLED  = "cancelled"

class ModelStatus:
    CONFIGURED     = "CONFIGURED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    FAILED         = "FAILED"
    LOADING        = "LOADING"
    UNAVAILABLE    = "UNAVAILABLE"

class DataAvailability:
    AVAILABLE             = "AVAILABLE"
    NOT_CONFIGURED        = "NOT_CONFIGURED"
    UNAVAILABLE           = "UNAVAILABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_CALCULABLE        = "NOT_CALCULABLE"
