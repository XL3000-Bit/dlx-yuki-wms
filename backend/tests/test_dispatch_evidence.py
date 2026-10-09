"""Real persisted mechanisms; explicitly TEST ONLY rules, no runtime gate substitute."""
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pytest
from fastapi import HTTPException
from app.models.dispatch_evidence import DispatchEvidencePolicy, DispatchEvidenceReview
from app.schemas.dispatch_evidence import EvidenceReviewWrite
from app.services import dispatch_evidence as evidence, load_dispatch_gate as gate
from app.services.picking_bol import generate_bol
from app.services.operational_document import register_generated_bol, archive_document
from test_dispatch_lifecycle import manifest, final_plan, execution, request, fba_manifest


def install_test_policy(db, m, *, version=1, enabled=True, seconds=3600, documents=None):
    import json
    if db.bind.dialect.name == 'sqlite': db.info['dispatch_owned_unit_test'] = True
    from app.services.dispatch_policy_config import SOURCE_FIELDS
    rule = {'roles': ['ADMIN'], 'valid_seconds': seconds}
    p = DispatchEvidencePolicy(warehouse_id=m.load.warehouse_id, business_type=m.load.dispatch_business_type,
        version=version, enabled=enabled, source=json.dumps({'purpose': 'TEST_ONLY',
            'confirmation_reference': 'TEST ONLY mechanism acceptance; no production authorization',
            'rule_sources': {key: 'TEST ONLY fixture decision' for key in SOURCE_FIELDS}}),
        rules={'documents': documents if documents is not None else [{'document_type': 'BOL', 'scope': 'ORDER', 'allow_generated': True, 'bol_statuses': [1]}],
               'document_review': dict(rule), 'approval': dict(rule), 'exception_review': dict(rule),
               'independent_approver': False, 'allow_canceled_exceptions': False},
        created_by=m.actor.id, created_at=datetime.now(timezone.utc))
    db.add(p); db.commit(); return p


def accept(db, m, kind, operation=None):
    v = evidence.evidence_view(db, m.actor, m.load.id)
    c = next(x for x in v['checks'] if x['kind'] == kind)
    payload = EvidenceReviewWrite(kind=kind, decision='ACCEPT', plan_id=v['plan_id'], content_revision=v['content_revision'],
        expected_fingerprint=c['fingerprint'], operation_id=operation or str(uuid4()), note='TEST ONLY: reviewed actual fixture evidence')
    return evidence.write_review(db, m.actor, m.load.id, payload), payload


def prepare(db, m, *, seconds=3600):
    p = final_plan(db, m); execution(db, m); install_test_policy(db, m, seconds=seconds)
    bol = generate_bol(db, m.order.id, m.actor.id)
    doc = register_generated_bol(db, bol, m.actor.id); db.commit()
    return p, doc


def approve_all(db, m):
    for kind in ('DOCUMENTS', 'EXCEPTIONS', 'APPROVAL'): accept(db, m, kind)


def test_generated_bol_registration_same_transaction_is_idempotent(db, manifest):
    from app.models.operational_document import OperationalDocument
    bol = generate_bol(db, manifest.order.id, manifest.actor.id, commit=False)
    first = register_generated_bol(db, bol, manifest.actor.id)
    second = register_generated_bol(db, bol, manifest.actor.id)
    db.commit()
    assert first.id == second.id
    assert db.query(OperationalDocument).filter_by(bol_id=bol.id).count() == 1


def test_configured_policy_requires_final_plan(db, manifest):
    install_test_policy(db, manifest)
    view = evidence.evidence_view(db, manifest.actor, manifest.load.id)
    assert all(c['reason'] == 'FINAL_PLAN_NOT_LOCKED' and not c['can_review'] for c in view['checks'])
    assert all(c['roles'] == ['ADMIN'] for c in view['checks'])


def test_foreign_warehouse_exception_blocks_without_disclosing_details(db, manifest):
    from app.models import Warehouse
    from app.models.operational_exception import OperationalException
    m = manifest; plan, _ = prepare(db, m); approve_all(db, m)
    wh = Warehouse(warehouse_code='FOREIGN-EX', warehouse_name='Foreign warehouse',
        address='Test only', city='Test', state='CA', zip_code='00000')
    db.add(wh); db.flush()
    ex = OperationalException(exception_no='FOREIGN-SECRET', title='Foreign confidential detail',
        warehouse_id=wh.id, load_id=m.load.id, reported_by=m.actor.id,
        exception_type='OUTBOUND', description='Foreign confidential detail', reported_at=datetime.now(timezone.utc))
    db.add(ex); db.commit()
    view = evidence.evidence_view(db, m.actor, m.load.id)
    assert any('EXCEPTION_SCOPE_MISMATCH' in x for c in view['checks'] for x in c['missing'])
    assert view['exceptions'] == [{'id': ex.id, 'status': 'SCOPE_MISMATCH', 'scope_mismatch': True}]
    with pytest.raises(HTTPException): gate.dispatch_load(db, m.actor, m.load.id, request(plan))
    assert m.load.status == 'READY'


@pytest.mark.parametrize('domain', ['PRIVATE', 'FBA'])
def test_persisted_evidence_dispatch_and_replay(db, manifest, domain):
    m = fba_manifest(db, manifest) if domain == 'FBA' else manifest
    plan, doc = prepare(db, m); approve_all(db, m)
    assert doc.dispatch_business_type == domain
    assert gate.integrated_readiness(db, m.actor, m.load.id).ready
    gate.dispatch_load(db, m.actor, m.load.id, request(plan))
    gate.dispatch_load(db, m.actor, m.load.id, request(plan))
    assert m.load.status == 'DISPATCHED' and m.order.status == 4
    assert db.query(DispatchEvidenceReview).count() == 3
    db.expire_all()
    view = evidence.evidence_view(db, m.actor, m.load.id)
    assert len(view['history']) == 3 and view['documents']
    assert all(not c['can_review'] for c in view['checks'])
    assert not gate.integrated_readiness(db, m.actor, m.load.id).ready
    c = view['checks'][0]
    with pytest.raises(HTTPException) as error:
        evidence.write_review(db, m.actor, m.load.id, EvidenceReviewWrite(
            kind=c['kind'], decision='ACCEPT', plan_id=view['plan_id'],
            content_revision=view['content_revision'], expected_fingerprint=c['fingerprint'],
            operation_id=str(uuid4()), note='Must remain read only after dispatch'))
    assert error.value.status_code == 403
    assert db.query(DispatchEvidenceReview).count() == 3


@pytest.mark.parametrize('change', ['archive', 'metadata', 'permission', 'disabled', 'plan'])
def test_changes_revoke_persisted_authorization(db, manifest, change):
    m = manifest; plan, doc = prepare(db, m); approve_all(db, m)
    if change == 'archive': archive_document(db, m.actor, doc)
    if change == 'metadata': m.load.trailer_no = 'changed'; db.commit()
    if change == 'permission': m.actor.is_active = False; db.commit()
    if change == 'disabled': install_test_policy(db, m, version=2, enabled=False)
    if change == 'plan':
        from app.models.load_dispatch import LoadDispatchPlan
        if db.bind.dialect.name == 'postgresql':
            from sqlalchemy.exc import IntegrityError
            db.get(LoadDispatchPlan, plan['id']).content_revision += 1
            with pytest.raises(IntegrityError): db.commit()
            db.rollback()
            with pytest.raises(HTTPException) as error:
                gate.dispatch_load(db, m.actor, m.load.id, request(dict(plan, content_revision=plan['content_revision'] + 1)))
            assert error.value.status_code == 409 and m.load.status == 'READY'
            return
        db.get(LoadDispatchPlan, plan['id']).content_revision += 1; db.commit()
    assert not gate.integrated_readiness(db, m.actor, m.load.id).ready
    with pytest.raises(HTTPException): gate.dispatch_load(db, m.actor, m.load.id, request(plan))
    assert m.load.status == 'READY'


def test_expired_review_blocks(db, manifest, monkeypatch):
    m = manifest; plan, _ = prepare(db, m, seconds=1); approve_all(db, m)
    class Future(datetime):
        @classmethod
        def now(cls, tz=None): return datetime.now(timezone.utc) + timedelta(seconds=5)
    monkeypatch.setattr(evidence, 'datetime', Future)
    assert any(c['reason'] == 'EVIDENCE_EXPIRED' for c in evidence.evidence_view(db, m.actor, m.load.id)['checks'])
    with pytest.raises(HTTPException): gate.dispatch_load(db, m.actor, m.load.id, request(plan))


def test_review_repeat_conflict_and_append_only(db, manifest):
    m = manifest; prepare(db, m)
    result, payload = accept(db, m, 'DOCUMENTS', 'repeat-review')
    assert evidence.write_review(db, m.actor, m.load.id, payload)['id'] == result['id']
    with pytest.raises(HTTPException) as err: evidence.write_review(db, m.actor, m.load.id, payload.model_copy(update={'note': 'changed'}))
    assert err.value.status_code == 409
    row = db.get(DispatchEvidenceReview, result['id']); row.note = 'tamper'
    with pytest.raises(ValueError): db.commit()
    db.rollback()


def test_active_exception_resolution_requires_attribution(db, manifest):
    from app.models.operational_exception import OperationalException, ExceptionStatus
    from app.services.operational_exception import transition_exception
    m = manifest; plan, _ = prepare(db, m)
    ex = OperationalException(exception_no='E-TEST', title='TEST ONLY damage investigation', warehouse_id=m.load.warehouse_id,
        load_id=m.load.id, reported_by=m.actor.id, exception_type='OUTBOUND', description='TEST ONLY', reported_at=datetime.now(timezone.utc))
    db.add(ex); db.commit()
    assert any('ACTIVE_EXCEPTIONS' in c['reason'] for c in evidence.evidence_view(db, m.actor, m.load.id)['checks'])
    with pytest.raises(HTTPException): accept(db, m, 'EXCEPTIONS')
    transition_exception(db, ex, ExceptionStatus.RESOLVED, m.actor.id, 'TEST ONLY inspection completed')
    approve_all(db, m)
    assert gate.integrated_readiness(db, m.actor, m.load.id).ready


def test_real_evidence_dispatch_failure_rolls_back(db, manifest, monkeypatch):
    from app.models.load_dispatch import LoadDispatchExecution
    from app.services import load
    m = manifest; plan, _ = prepare(db, m); approve_all(db, m)
    monkeypatch.setattr(load, 'sync_load_notification', lambda *args: (_ for _ in ()).throw(RuntimeError('test rollback')))
    with pytest.raises(RuntimeError): gate.dispatch_load(db, m.actor, m.load.id, request(plan))
    db.expire_all()
    assert m.load.status == 'READY' and m.order.status == 3
    assert db.query(LoadDispatchExecution).count() == 0
    assert db.query(DispatchEvidenceReview).count() == 3


def test_unconfigured_and_viewer_cannot_review(db, client, manifest, seed):
    from app.core.security import create_access_token
    m = manifest; plan = final_plan(db, m)
    payload = {'kind':'DOCUMENTS','decision':'ACCEPT','plan_id':plan['id'],'content_revision':plan['content_revision'],
               'expected_fingerprint':'0'*64,'operation_id':'unknown-review','note':'Test'}
    assert client.post(f'/api/v1/loads/{m.load.id}/evidence/reviews', json=payload).status_code == 409
    client.headers['Authorization'] = f"Bearer {create_access_token(str(seed['viewer'].id))}"
    assert client.post(f'/api/v1/loads/{m.load.id}/evidence/reviews', json=payload).status_code in (403, 409)
