"""Explicit offline policy publication. Nothing is loaded at application startup."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text

from app.models import AuditLog, User, Warehouse
from app.models.user import UserRole, ScopeMode
from app.models.dispatch_evidence import DispatchEvidencePolicy
from app.schemas.dispatch_evidence import EvidenceRules

SOURCE_FIELDS = ('documents', 'document_review', 'approval', 'exception_review',
                 'independent_approver', 'allow_canceled_exceptions')


def authenticate_operator(db, username, password):
    """Authenticate the operator before applying persisted role and scope checks.

    An audit user ID is never an authentication credential. Use the same password
    verifier as the application's login endpoint and fail closed on legacy hashes.
    """
    from app.core.security import verify_password
    from pwdlib.exceptions import UnknownHashError
    actor = db.scalar(select(User).where(User.username == username).execution_options(populate_existing=True))
    valid = False
    if actor is not None and actor.is_active:
        try:
            valid = verify_password(password, actor.password_hash)
        except (ValueError, TypeError, UnknownHashError):
            pass
    if not valid:
        raise HTTPException(401, 'Operator authentication failed')
    return actor


class Provenance(BaseModel):
    model_config = ConfigDict(extra='forbid')
    purpose: Literal['PRODUCTION', 'TEST_ONLY']
    confirmation_reference: str = Field(min_length=1)
    rule_sources: dict[str, str]

    @model_validator(mode='after')
    def complete_sources(self):
        if set(self.rule_sources) != set(SOURCE_FIELDS) or any(not v.strip() for v in self.rule_sources.values()):
            raise ValueError('Each rule group requires its confirmed source')
        if not self.confirmation_reference.strip():
            raise ValueError('Confirmation reference is required')
        if self.purpose == 'PRODUCTION' and any('TEST ONLY' in v.upper() or 'TEST_ONLY' in v.upper()
                for v in [self.confirmation_reference, *self.rule_sources.values()]):
            raise ValueError('Test references cannot authorize a production policy')
        return self


class PolicyDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    warehouse_id: int = Field(gt=0)
    business_type: Literal['FBA', 'PRIVATE']
    expected_version: int = Field(ge=0)
    provenance: Provenance
    rules: EvidenceRules


def isolated_runtime(db):
    """Environment flag alone cannot opt an application into test policies."""
    if db.bind.dialect.name == 'sqlite':
        return db.info.get('dispatch_owned_unit_test') is True
    from app.core.config import settings
    if settings.environment != 'dispatch-isolated-test' or db.bind.dialect.name != 'postgresql':
        return False
    if db.scalar(text('SELECT current_user')) != 'codex_dispatch_test':
        return False
    data = Path(db.scalar(text('SHOW data_directory'))).resolve()
    root = Path(__file__).resolve().parents[3]
    try:
        return data.parent.name.startswith(('yuki-dispatch-pg-', 'yuki-dispatch-browser-')) and (
            data.parent / 'owned-by-dispatch-verification').read_text(encoding='utf-8') == str(root)
    except OSError:
        return False


def source_allowed(db, source):
    try:
        provenance = Provenance.model_validate_json(source)
    except ValueError:
        return False
    return provenance.purpose == 'PRODUCTION' or isolated_runtime(db)


def template(business_type):
    if business_type not in ('FBA', 'PRIVATE'):
        raise ValueError('Choose FBA or PRIVATE')
    return dict(warehouse_id=None, business_type=business_type, expected_version=None,
        provenance=dict(purpose='PRODUCTION', confirmation_reference=None,
                        rule_sources={name: None for name in SOURCE_FIELDS}),
        rules=dict(documents=[dict(document_type=None, scope=None, allow_generated=None, bol_statuses=None)],
                   document_review=dict(roles=None, valid_seconds=None),
                   approval=dict(roles=None, valid_seconds=None),
                   exception_review=dict(roles=None, valid_seconds=None),
                   independent_approver=None, allow_canceled_exceptions=None))


def latest(db, warehouse_id, business_type):
    return db.scalar(select(DispatchEvidencePolicy).where(DispatchEvidencePolicy.warehouse_id == warehouse_id,
        DispatchEvidencePolicy.business_type == business_type).order_by(DispatchEvidencePolicy.version.desc()).limit(1))


def authorize(db, actor, warehouse_id):
    actor = db.get(User, actor.id, populate_existing=True)
    if not actor or not actor.is_active or actor.role != UserRole.ADMIN:
        raise HTTPException(403, 'Policy publication requires an active ADMIN')
    db.expire(actor, ['warehouses'])
    if actor.warehouse_scope_mode == ScopeMode.SELECTED and warehouse_id not in actor.warehouse_ids:
        raise HTTPException(403, 'Warehouse outside publisher scope')
    if not db.get(Warehouse, warehouse_id):
        raise HTTPException(404, 'Warehouse not found')


def preview(db, actor, raw):
    draft = PolicyDraft.model_validate(raw)
    authorize(db, actor, draft.warehouse_id)
    if not source_allowed(db, draft.provenance.model_dump_json()):
        raise HTTPException(409, 'TEST_ONLY policy requires a verified owned isolated runtime')
    old = latest(db, draft.warehouse_id, draft.business_type)
    version = old.version if old else 0
    if draft.expected_version != version:
        raise HTTPException(409, 'Policy version changed; refresh the diff')
    before = old.rules if old else {}
    after = draft.rules.model_dump(mode='json')
    differences = {key: {'before': before.get(key), 'after': after.get(key)}
                   for key in SOURCE_FIELDS if before.get(key) != after.get(key)}
    return draft, dict(warehouse_id=draft.warehouse_id, business_type=draft.business_type,
        current_version=version, proposed_version=version + 1, differences=differences,
        provenance=draft.provenance.model_dump(), current_enabled=old.enabled if old else False,
        pending_fields=[], warning='Publication changes invalidate existing reviews; dry-run writes nothing')


def publish(db, actor, raw, *, revoke=False):
    from app.services.dispatch_evidence import evidence_lock
    try:
        evidence_lock(db)
        draft, diff = preview(db, actor, raw)
        previous = latest(db, draft.warehouse_id, draft.business_type)
        if revoke and previous is None:
            raise HTTPException(409, 'No policy to revoke')
        row = DispatchEvidencePolicy(warehouse_id=draft.warehouse_id, business_type=draft.business_type,
            version=diff['proposed_version'], enabled=not revoke,
            source=draft.provenance.model_dump_json(), rules=draft.rules.model_dump(mode='json'),
            created_by=actor.id, created_at=datetime.now(timezone.utc))
        db.add(row); db.flush()
        db.add(AuditLog(user_id=actor.id, action='REVOKE' if revoke else 'PUBLISH',
            entity_type='dispatch_evidence_policy', entity_id=row.id,
            before_data={'policy_id': previous.id if previous else None, 'version': diff['current_version']},
            after_data={**diff, 'enabled': row.enabled, 'policy_id': row.id}))
        db.commit()
        return {'policy_id': row.id, 'version': row.version, 'enabled': row.enabled}
    except Exception:
        db.rollback()
        raise
