"""
SATQUERY AI — Database Models v2
Expanded schema with ModelExecution, AgentRun, Evidence, AuditLog, OTPRequest.
Compatible with SQLite (dev) and PostgreSQL (prod).
Uses Alembic for migrations — do NOT call db.create_all() in production.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _uuid() -> str:
    return str(uuid.uuid4())


# ── User ──────────────────────────────────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"

    id               = db.Column(db.String(36), primary_key=True, default=_uuid)
    full_name        = db.Column(db.String(128), nullable=False)
    email            = db.Column(db.String(256), unique=True, nullable=False, index=True)
    password_hash    = db.Column(db.String(256), nullable=False)
    preferred_language = db.Column(db.String(32), default="en")
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    last_login       = db.Column(db.DateTime, nullable=True)
    is_active        = db.Column(db.Boolean, default=True)
    # OTP flow
    mobile_number    = db.Column(db.String(20), nullable=True)

    analyses   = db.relationship("Analysis",    backref="user", lazy="dynamic", cascade="all, delete-orphan")
    audit_logs = db.relationship("AuditLog",    backref="user", lazy="dynamic", cascade="all, delete-orphan")
    otp_requests = db.relationship("OTPRequest", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id":                 self.id,
            "full_name":          self.full_name,
            "email":              self.email,
            "preferred_language": self.preferred_language,
            "created_at":         self.created_at.isoformat() if self.created_at else None,
            "last_login":         self.last_login.isoformat()  if self.last_login  else None,
            "has_mobile":         bool(self.mobile_number),
            "analysis_count":     self.analyses.count(),
        }


# ── Analysis ──────────────────────────────────────────────────────────────────

class Analysis(db.Model):
    __tablename__ = "analyses"

    id           = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id      = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)

    mode         = db.Column(db.String(32), nullable=False)   # single | optical_sar | multitemporal
    input_type   = db.Column(db.String(16), nullable=False, default="image")  # image | coordinates

    latitude     = db.Column(db.Float,       nullable=True)
    longitude    = db.Column(db.Float,       nullable=True)
    place_name   = db.Column(db.String(512), nullable=True)

    before_date  = db.Column(db.String(32),  nullable=True)
    before_time  = db.Column(db.String(16),  nullable=True)
    after_date   = db.Column(db.String(32),  nullable=True)
    after_time   = db.Column(db.String(16),  nullable=True)

    image1_path  = db.Column(db.String(512), nullable=True)
    image2_path  = db.Column(db.String(512), nullable=True)

    nl_query     = db.Column(db.Text, nullable=True)
    nl_answer    = db.Column(db.Text, nullable=True)

    # Lifecycle: created → queued → processing → validating → completed | failed | cancelled
    status       = db.Column(db.String(16), default="created", index=True)
    error_message = db.Column(db.Text,      nullable=True)

    result_json  = db.Column(db.Text,  nullable=True)
    overall_confidence = db.Column(db.Float, nullable=True)
    report_path  = db.Column(db.String(512), nullable=True)

    # RQ job tracking
    rq_job_id    = db.Column(db.String(64), nullable=True)

    created_at   = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    uploaded_images  = db.relationship("UploadedImage",  backref="analysis", lazy="dynamic", cascade="all, delete-orphan")
    agent_runs       = db.relationship("AgentRun",       backref="analysis", lazy="dynamic", cascade="all, delete-orphan")
    model_executions = db.relationship("ModelExecution", backref="analysis", lazy="dynamic", cascade="all, delete-orphan")
    evidence_items   = db.relationship("Evidence",       backref="analysis", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self, include_result: bool = False) -> dict:
        d = {
            "id":                self.id,
            "user_id":           self.user_id,
            "mode":              self.mode,
            "input_type":        self.input_type,
            "latitude":          self.latitude,
            "longitude":         self.longitude,
            "place_name":        self.place_name,
            "before_date":       self.before_date,
            "before_time":       self.before_time,
            "after_date":        self.after_date,
            "after_time":        self.after_time,
            "nl_query":          self.nl_query,
            "nl_answer":         self.nl_answer,
            "status":            self.status,
            "error_message":     self.error_message,
            "overall_confidence": self.overall_confidence,
            "has_report":        bool(self.report_path),
            "rq_job_id":         self.rq_job_id,
            "created_at":        self.created_at.isoformat()   if self.created_at   else None,
            "completed_at":      self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_result and self.result_json:
            try:
                d["result"] = json.loads(self.result_json)
            except Exception:
                d["result"] = None
        return d


# ── Uploaded Image ────────────────────────────────────────────────────────────

class UploadedImage(db.Model):
    __tablename__ = "uploaded_images"

    id                = db.Column(db.String(36), primary_key=True, default=_uuid)
    analysis_id       = db.Column(db.String(36), db.ForeignKey("analyses.id"), nullable=False)
    role              = db.Column(db.String(32), nullable=False)
    original_filename = db.Column(db.String(256), nullable=False)
    stored_filename   = db.Column(db.String(256), nullable=False)
    file_size_bytes   = db.Column(db.Integer, nullable=True)
    mime_type         = db.Column(db.String(64), nullable=True)
    width_px          = db.Column(db.Integer, nullable=True)
    height_px         = db.Column(db.Integer, nullable=True)
    has_georeference  = db.Column(db.Boolean, default=False)
    crs               = db.Column(db.String(64), nullable=True)
    pixel_size_m      = db.Column(db.Float,   nullable=True)
    uploaded_at       = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "role": self.role,
            "original_filename": self.original_filename,
            "file_size_bytes": self.file_size_bytes,
            "width_px": self.width_px, "height_px": self.height_px,
            "has_georeference": self.has_georeference, "crs": self.crs,
            "pixel_size_m": self.pixel_size_m,
        }


# ── ModelExecution ────────────────────────────────────────────────────────────

class ModelExecution(db.Model):
    """Records each time a ML model was called — enables full reproducibility."""
    __tablename__ = "model_executions"

    id               = db.Column(db.String(36), primary_key=True, default=_uuid)
    analysis_id      = db.Column(db.String(36), db.ForeignKey("analyses.id"), nullable=False, index=True)
    model_name       = db.Column(db.String(128), nullable=False)
    model_identifier = db.Column(db.String(256), nullable=False)
    model_version    = db.Column(db.String(64),  nullable=True)
    task             = db.Column(db.String(64),  nullable=False)
    device           = db.Column(db.String(32),  nullable=True)   # cpu | cuda:0
    status           = db.Column(db.String(32),  nullable=False)  # success | failed | not_configured
    execution_time_s = db.Column(db.Float,       nullable=True)
    input_ref        = db.Column(db.String(512), nullable=True)   # image path or asset ID
    output_json      = db.Column(db.Text,        nullable=True)   # serialised ModelOutput.data
    error            = db.Column(db.Text,        nullable=True)
    started_at       = db.Column(db.DateTime,    default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "model_name": self.model_name,
            "model_identifier": self.model_identifier,
            "task": self.task, "device": self.device,
            "status": self.status,
            "execution_time_s": self.execution_time_s,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
        }


# ── AgentRun ──────────────────────────────────────────────────────────────────

class AgentRun(db.Model):
    """Records each agent stage executed in the pipeline."""
    __tablename__ = "agent_runs"

    id          = db.Column(db.String(36), primary_key=True, default=_uuid)
    analysis_id = db.Column(db.String(36), db.ForeignKey("analyses.id"), nullable=False, index=True)
    stage_name  = db.Column(db.String(64),  nullable=False)
    stage_index = db.Column(db.Integer,     nullable=True)
    status      = db.Column(db.String(32),  nullable=False)   # success | failed | skipped
    duration_s  = db.Column(db.Float,       nullable=True)
    output_json = db.Column(db.Text,        nullable=True)
    error       = db.Column(db.Text,        nullable=True)
    ran_at      = db.Column(db.DateTime,    default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "stage_name": self.stage_name,
            "stage_index": self.stage_index, "status": self.status,
            "duration_s": self.duration_s, "error": self.error,
            "ran_at": self.ran_at.isoformat() if self.ran_at else None,
        }


# ── Evidence ──────────────────────────────────────────────────────────────────

class Evidence(db.Model):
    """Validated analytical measurement with full provenance."""
    __tablename__ = "evidence"

    id                   = db.Column(db.String(36), primary_key=True, default=_uuid)
    analysis_id          = db.Column(db.String(36), db.ForeignKey("analyses.id"), nullable=False, index=True)
    claim_type           = db.Column(db.String(64), nullable=False)    # building_count | water_pct | change_pct …
    value_json           = db.Column(db.Text,       nullable=True)     # serialised value (may be null = unavailable)
    status               = db.Column(db.String(32), nullable=False)    # valid | unavailable | insufficient
    source               = db.Column(db.String(128), nullable=True)    # model name or method
    source_execution_id  = db.Column(db.String(36),  nullable=True)    # FK to model_executions.id
    derived_from         = db.Column(db.String(512), nullable=True)    # asset path
    calculation          = db.Column(db.String(256), nullable=True)    # formula description
    confidence           = db.Column(db.Float,       nullable=True)
    note                 = db.Column(db.Text,        nullable=True)
    created_at           = db.Column(db.DateTime,    default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "claim_type": self.claim_type,
            "value": json.loads(self.value_json) if self.value_json else None,
            "status": self.status, "source": self.source,
            "source_execution_id": self.source_execution_id,
            "calculation": self.calculation,
            "confidence": self.confidence, "note": self.note,
        }


# ── AuditLog ──────────────────────────────────────────────────────────────────

class AuditLog(db.Model):
    """Immutable audit trail for security-relevant events."""
    __tablename__ = "audit_logs"

    id         = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id    = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True, index=True)
    event      = db.Column(db.String(64),  nullable=False, index=True)   # login | logout | register | delete_analysis …
    ip_address = db.Column(db.String(45),  nullable=True)
    user_agent = db.Column(db.String(256), nullable=True)
    detail     = db.Column(db.Text,        nullable=True)   # JSON — never log passwords/tokens
    success    = db.Column(db.Boolean,     nullable=False, default=True)
    occurred_at = db.Column(db.DateTime,   default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "event": self.event,
            "ip_address": self.ip_address, "success": self.success,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
        }


# ── OTPRequest ────────────────────────────────────────────────────────────────

class OTPRequest(db.Model):
    """Tracks OTP send/verify attempts for password reset."""
    __tablename__ = "otp_requests"

    id            = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id       = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    mobile_number = db.Column(db.String(20), nullable=False)
    # OTP hash stored, never plaintext
    otp_hash      = db.Column(db.String(256), nullable=False)
    expires_at    = db.Column(db.DateTime,   nullable=False)
    used          = db.Column(db.Boolean,    default=False)
    attempts      = db.Column(db.Integer,    default=0)
    created_at    = db.Column(db.DateTime,   default=datetime.utcnow)
    provider_ref  = db.Column(db.String(128), nullable=True)  # provider message ID

    def is_expired(self) -> bool:
        return datetime.utcnow() >= self.expires_at

    def is_valid(self) -> bool:
        return not self.used and not self.is_expired() and self.attempts < 5
