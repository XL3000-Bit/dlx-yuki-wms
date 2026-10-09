"""Offline publication and fail-closed runtime provenance, not business authorization."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app.models import AuditLog
from app.models.dispatch_evidence import DispatchEvidencePolicy
from app.models.user import ScopeMode
from app.services import dispatch_policy_config as config, dispatch_evidence as evidence
from test_dispatch_lifecycle import manifest
from test_dispatch_evidence import install_test_policy


def draft(db, m):
    p = install_test_policy(db, m)
    return dict(warehouse_id=m.load.warehouse_id, business_type=m.load.dispatch_business_type,
                expected_version=p.version, provenance=json.loads(p.source), rules=p.rules)


def test_operator_requires_credentials_and_persisted_permission(db, manifest, seed):
    password = 'WarehousePassword!'
    assert config.authenticate_operator(db, 'admin', password).id == seed['admin'].id
    for username, secret in [('admin', 'wrong'), ('missing', password)]:
        with pytest.raises(HTTPException) as error:
            config.authenticate_operator(db, username, secret)
        assert error.value.status_code == 401
    viewer = config.authenticate_operator(db, 'viewer', password)
    with pytest.raises(HTTPException) as error:
        config.preview(db, viewer, draft(db, manifest))
    assert error.value.status_code == 403
    seed['admin'].is_active = False
    db.commit()
    with pytest.raises(HTTPException) as error:
        config.authenticate_operator(db, 'admin', password)
    assert error.value.status_code == 401
    seed['admin'].is_active = True
    seed['admin'].password_hash = 'historical-unusable-hash'
    db.commit()
    with pytest.raises(HTTPException) as error:
        config.authenticate_operator(db, 'admin', password)
    assert error.value.status_code == 401


@pytest.mark.parametrize('domain', ['FBA', 'PRIVATE'])
def test_templates_cannot_authorize(domain):
    with pytest.raises(ValidationError): config.PolicyDraft.model_validate(config.template(domain))


@pytest.mark.parametrize('field,value', [('roles', []), ('roles', ['ADMIN', 'ADMIN']),
    ('roles', ['UNKNOWN']), ('valid_seconds', 0), ('valid_seconds', 31536001)])
def test_invalid_rules(db, manifest, field, value):
    raw = copy.deepcopy(draft(db, manifest))
    raw['rules']['approval'][field] = value
    with pytest.raises(ValidationError): config.PolicyDraft.model_validate(raw)


def test_preview_publish_revoke_and_audit(db, manifest):
    raw = draft(db, manifest)
    raw['rules']['approval']['valid_seconds'] = 1800
    count = db.query(DispatchEvidencePolicy).count()
    diff = config.preview(db, manifest.actor, raw)[1]
    assert diff['differences'] == {'approval': {'before': {'roles': ['ADMIN'], 'valid_seconds': 3600},
                                              'after': {'roles': ['ADMIN'], 'valid_seconds': 1800}}}
    assert db.query(DispatchEvidencePolicy).count() == count
    assert config.publish(db, manifest.actor, raw)['version'] == 2
    with pytest.raises(HTTPException) as error: config.publish(db, manifest.actor, raw)
    assert error.value.status_code == 409
    raw['expected_version'] = 2
    assert config.publish(db, manifest.actor, raw, revoke=True)['enabled'] is False
    assert evidence.policy(db, manifest.load)[1] is None
    assert db.query(DispatchEvidencePolicy).count() == count + 2
    assert [r.action for r in db.query(AuditLog).filter_by(entity_type='dispatch_evidence_policy').order_by(AuditLog.id)] == ['PUBLISH', 'REVOKE']


def test_scope_role_and_failed_publication_rollback(db, manifest, seed, monkeypatch):
    raw = draft(db, manifest)
    with pytest.raises(HTTPException) as error: config.preview(db, seed['viewer'], raw)
    assert error.value.status_code == 403
    manifest.actor.warehouse_scope_mode = ScopeMode.SELECTED
    manifest.actor.warehouses = []
    db.commit()
    with pytest.raises(HTTPException) as error: config.preview(db, manifest.actor, raw)
    assert error.value.status_code == 403
    manifest.actor.warehouse_scope_mode = ScopeMode.ALL
    db.commit()
    count = db.query(DispatchEvidencePolicy).count()
    def fail(): raise RuntimeError('TEST ONLY commit failure')
    monkeypatch.setattr(db, 'commit', fail)
    with pytest.raises(RuntimeError): config.publish(db, manifest.actor, raw)
    assert db.query(DispatchEvidencePolicy).count() == count
    assert db.query(AuditLog).filter_by(entity_type='dispatch_evidence_policy').count() == 0


def test_test_policy_fails_closed_without_owned_runtime(db, manifest, monkeypatch):
    raw = draft(db, manifest)
    db.info.pop('dispatch_owned_unit_test', None)
    from app.core.config import settings
    monkeypatch.setattr(settings, 'environment', 'dispatch-isolated-test')
    assert not config.source_allowed(db, json.dumps(raw['provenance']))
    assert evidence.policy(db, manifest.load)[1] is None
    with pytest.raises(HTTPException): config.preview(db, manifest.actor, raw)
    assert not config.source_allowed(db, 'TEST ONLY old plain source')
    raw['provenance']['purpose'] = 'PRODUCTION'
    with pytest.raises(ValidationError): config.PolicyDraft.model_validate(raw)


@pytest.mark.parametrize('domain', ['FBA', 'PRIVATE'])
def test_cli_template_and_validation_are_offline(tmp_path, domain):
    script = Path(__file__).resolve().parents[2] / 'scripts' / 'dispatch_policy.py'
    env = {key: value for key, value in os.environ.items()
           if key.upper() not in ('DATABASE_URL', 'WMS_ENV', 'ENVIRONMENT', 'PYTHONPATH')}
    result = subprocess.run([sys.executable, str(script), 'template', '--business', domain],
                            cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    raw = json.loads(result.stdout)
    assert raw == config.template(domain)
    file = tmp_path / 'draft.json'
    file.write_text(result.stdout, encoding='utf-8')
    result = subprocess.run([sys.executable, str(script), 'validate', '--file', str(file)],
                            cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 2
    fields = json.loads(result.stderr)['pending_or_invalid_fields']
    assert any(item['field'] == 'warehouse_id' for item in fields)
    assert not any('database_url' in item['field'] for item in fields)
