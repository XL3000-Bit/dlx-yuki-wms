"""Create an owned loopback PostgreSQL cluster; never read the project database URL.

Run with backend/.venv/Scripts/python.exe scripts/verify_dispatch_isolated.py.
Retains the stopped cluster/logs in TEMP for inspection. Policy success cases use
an explicitly test-only substitute; the real policy gate must remain blocked.
"""
from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def parent():
    bins = Path(os.environ.get('YUKI_TEST_PG_BIN', r'C:\Program Files\PostgreSQL\17\bin'))
    if not (bins / 'initdb.exe').is_file():
        raise SystemExit('Isolated PostgreSQL binaries unavailable')
    workspace = Path(tempfile.mkdtemp(prefix='yuki-dispatch-pg-'))
    data = workspace / 'data'
    (workspace / 'owned-by-dispatch-verification').write_text(str(ROOT), encoding='utf-8')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    def run(*args):
        with (workspace / 'cluster.log').open('a', encoding='utf-8') as log:
            # Windows postmaster inherits handles; pipes keep communicate() waiting
            # after pg_ctl exits. A file is safe for both parent and server output.
            result = subprocess.run([str(arg) for arg in args], stdout=log, stderr=log,
                                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=120)
        if result.returncode:
            raise RuntimeError(f'Isolated PostgreSQL command failed; inspect {workspace / "cluster.log"}')
    started = False
    try:
        run(bins / 'initdb.exe', '-D', data, '-U', 'codex_dispatch_test', '-A', 'trust', '--encoding=UTF8', '--locale=C')
        run(bins / 'pg_ctl.exe', '-D', data, '-l', workspace / 'server.log', '-o', f'-h 127.0.0.1 -p {port}', '-w', 'start')
        started = True
        env = dict(os.environ, DATABASE_URL=f'postgresql+psycopg://codex_dispatch_test@127.0.0.1:{port}/postgres', PYTHONUTF8='1', WMS_ENV='dispatch-isolated-test')
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker', str(data)], env=env, cwd=ROOT)
        if result.returncode:
            raise SystemExit(result.returncode)
    finally:
        if started:
            run(bins / 'pg_ctl.exe', '-D', data, '-m', 'fast', '-w', 'stop')
        print(f'Owned isolated cluster stopped; evidence: {workspace}', flush=True)


def worker(data: Path):
    sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'backend' / 'tests')]
    import pytest
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from alembic import command
    from alembic.config import Config
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi import HTTPException
    import conftest
    import test_dispatch_lifecycle as cases
    from app.models import User, AuditLog
    from app.models.user import ScopeMode, UserRole
    from app.models.load_dispatch import LoadAllocation, LoadDispatchExecution
    from app.schemas.load_dispatch_write import AllocationWrite
    from app.services import load_dispatch_write as writer, load_dispatch_gate as gate

    url = os.environ['DATABASE_URL']
    admin = create_engine(url, isolation_level='AUTOCOMMIT')
    with admin.connect() as connection:
        actual = Path(connection.scalar(text('SHOW data_directory'))).resolve()
        assert actual == data.resolve() and (actual.parent / 'owned-by-dispatch-verification').read_text(encoding='utf-8') == str(ROOT)
        assert connection.scalar(text('SELECT current_user')) == 'codex_dispatch_test'
        connection.execute(text('CREATE DATABASE dispatch_template'))
    template_url = url.rsplit('/', 1)[0] + '/dispatch_template'
    template = create_engine(template_url)
    config = Config(str(ROOT / 'backend' / 'alembic.ini'))
    config.set_main_option('script_location', str(ROOT / 'backend' / 'alembic'))
    # Alembic owns the transaction, including historical enum autocommit blocks.
    with template.connect() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
    with template.connect() as connection:
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '20261005_0039'
    template.dispose()
    print('PASS migration 0001..0039 on owned PostgreSQL cluster', flush=True)
    total = 0

    def run_case(name, body):
        nonlocal total
        dbname = f'dispatch_case_{total}'
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE {dbname} TEMPLATE dispatch_template'))
        engine = create_engine(url.rsplit('/', 1)[0] + '/' + dbname)
        sessions = sessionmaker(bind=engine, expire_on_commit=False)
        try:
            with sessions() as db, pytest.MonkeyPatch.context() as patch:
                seed = conftest.seed.__wrapped__(db)
                manifest = cases.manifest.__wrapped__(db, seed)
                body(db, manifest, patch, sessions, seed)
            total += 1
            print(f'PASS {name}', flush=True)
        finally:
            engine.dispose()

    run_case('real UNKNOWN policies block with real loading evidence', lambda db, m, p, s, seed: cases.test_real_evidence_still_blocks_unconfirmed_policies(db, m))
    run_case('synthetic policy mechanics: success and exact replay', lambda db, m, p, s, seed: cases.test_transaction_success_and_exact_replay_with_synthetic_policy(db, m, p))
    run_case('missing execution and stale revision', lambda db, m, p, s, seed: cases.test_missing_execution_and_stale_revision_block(db, m, p))
    run_case('injected failure rolls back status, execution and audit', lambda db, m, p, s, seed: cases.test_failure_rolls_back_status_execution_and_audit(db, m, p))
    run_case('FINAL plan and reservation frozen', lambda db, m, p, s, seed: cases.test_final_plan_and_reservation_are_frozen(db, m))
    run_case('manifest edit invalidates verification', lambda db, m, p, s, seed: cases.test_metadata_change_invalidates_verification(db, m))

    def scope(db, m, patch, sessions, seed):
        restricted = User(username='restricted', display_name='Restricted', email='restricted@test.invalid', password_hash='test-only', role=UserRole.MANAGER,
                          warehouse_scope_mode=ScopeMode.SELECTED, customer_scope_mode=ScopeMode.SELECTED)
        db.add(restricted); db.commit()
        for action in (lambda: writer.create_plan(db, restricted, m.load.id), lambda: gate.dispatch_load(db, restricted, m.load.id, cases.request({'id': 1, 'content_revision': 0}))):
            with pytest.raises(HTTPException) as error:
                action()
            assert error.value.status_code == 404
            db.rollback()
    run_case('out-of-scope manager cannot write or dispatch', scope)
    for field in ('warehouse', 'customer', 'business', 'quantity', 'ownership'):
        run_case(f'admin cannot bypass {field}', lambda db, m, p, s, seed, field=field: cases.test_inventory_ownership_and_quantity_enforced_for_admin(db, m, field))

    def race(db, m, patch, sessions, seed, same_operation):
        plan = cases.final_plan(db, m); cases.execution(db, m); cases.synthetic_policies(patch)
        actor_id, load_id = m.actor.id, m.load.id
        db.rollback()
        barrier = Barrier(2)
        def dispatch(index):
            with sessions() as session:
                actor = session.get(User, actor_id)
                barrier.wait(timeout=15)
                try:
                    gate.dispatch_load(session, actor, load_id, cases.request(plan, 'race-same' if same_operation else f'race-{index}'))
                    return 'success'
                except HTTPException as error:
                    assert error.status_code == 409
                    return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(dispatch, (1, 2)))
        assert sorted(outcomes) == (['success', 'success'] if same_operation else ['conflict', 'success'])
        db.expire_all()
        assert db.query(LoadDispatchExecution).count() == 1
        assert db.query(AuditLog).filter_by(action='LOAD_DISPATCH').count() == 1
        assert m.load.status == 'DISPATCHED' and m.order.status == 4
    run_case('concurrent identical request commits once', lambda db, m, p, s, seed: race(db, m, p, s, seed, True))
    run_case('concurrent distinct dispatch requests have one winner', lambda db, m, p, s, seed: race(db, m, p, s, seed, False))

    def allocation_race(db, m, patch, sessions, seed):
        actor_id, load_id, inv_id = m.actor.id, m.load.id, m.inv.id
        db.rollback(); barrier = Barrier(2)
        def allocate(index):
            with sessions() as session:
                actor = session.get(User, actor_id)
                barrier.wait(timeout=15)
                try:
                    writer.write_allocation(session, actor, load_id, AllocationWrite(inventory_allocation_id=inv_id, carton_qty=0, pallet_qty=4, operation_id=f'race-allocation-{index}'))
                    return 'success'
                except HTTPException as error:
                    assert error.status_code == 409
                    return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(allocate, (1, 2)))
        assert sorted(outcomes) == ['conflict', 'success']
        assert db.query(LoadAllocation).count() == 1
    run_case('concurrent allocation cannot over-reserve inventory', allocation_race)

    run_case('FBA real policy blockers remain enforced', lambda db, m, p, s, seed: cases.test_fba_real_policies_block(db, m))
    run_case('FBA dispatch and downstream conservation', lambda db, m, p, s, seed: cases.test_fba_dispatch_completion_conserves_all_units(db, m, p))
    run_case('FBA upstream release waits for outbound release', lambda db, m, p, s, seed: cases.test_fba_upstream_release_waits_for_outbound_release(db, m))
    run_case('FBA ownership and completion guarded', lambda db, m, p, s, seed: cases.test_fba_ownership_and_completion_are_guarded(db, m))
    for unit in ('pallet_qty', 'carton_qty', 'weight_lbs', 'cbm'):
        run_case(f'FBA source reservation conserved: {unit}', lambda db, m, p, s, seed, unit=unit: cases.test_fba_source_cannot_be_over_reserved(db, m, unit))
    run_case('corrupt inventory completion rolls back', lambda db, m, p, s, seed: cases.test_corrupt_completion_fails_without_clamping_inventory(db, m, p))
    run_case('shared lot aggregate reservation guarded', lambda db, m, p, s, seed: cases.test_shared_lot_cannot_hide_extra_private_reservations(db, m))

    def completion_race(db, m, patch, sessions, seed):
        from app.services import outbound
        m = cases.fba_manifest(db, m)
        plan = cases.final_plan(db, m); cases.execution(db, m); cases.synthetic_policies(patch)
        gate.dispatch_load(db, m.actor, m.load.id, cases.request(plan))
        order_id, actor_id = m.order.id, m.actor.id
        db.rollback(); barrier = Barrier(2)
        def complete(index):
            with sessions() as session:
                barrier.wait(timeout=15)
                try:
                    outbound.change(session, order_id, 5, actor_id)
                    return 'success'
                except HTTPException as error:
                    assert error.status_code in (400, 409)
                    return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(complete, (1, 2)))
        assert sorted(outcomes) == ['conflict', 'success']
        db.expire_all()
        assert m.order.status == 5 and m.inv.completed_pallet_qty == 4
        assert m.lot.allocated_pallet_qty == 0 and m.source.allocated_pallet_qty == 0
    run_case('concurrent downstream completion consumes once', completion_race)

    def source_release_race(db, m, patch, sessions, seed):
        from app.services import outbound, fba
        from app.schemas.outbound import AllocateRequest
        from app.schemas.fba import ReleaseRequest
        m = cases.fba_manifest(db, m)
        m.inv.allocated_pallet_qty = 0
        db.commit()
        order_id, source_id, shipment_id, lot_id, actor_id = m.order.id, m.source.id, m.source.fba_shipment_id, m.lot.id, m.actor.id
        db.rollback(); barrier = Barrier(2)
        def mutate(index):
            with sessions() as session:
                barrier.wait(timeout=15)
                try:
                    if index == 1:
                        outbound.allocate(session, order_id, AllocateRequest(inventory_lot_id=lot_id, fba_allocation_id=source_id, pallet_qty=4), actor_id)
                    else:
                        fba.release(session, shipment_id, source_id, ReleaseRequest(), actor_id)
                    return 'success'
                except HTTPException as error:
                    assert error.status_code == 409
                    return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(mutate, (1, 2)))
        assert sorted(outcomes) == ['conflict', 'success']
        db.expire_all()
        assert m.source.allocated_pallet_qty >= m.inv.allocated_pallet_qty - m.inv.completed_pallet_qty
        assert m.lot.allocated_pallet_qty == m.source.allocated_pallet_qty
    run_case('FBA source release versus outbound allocation serializes', source_release_race)
    import test_dispatch_evidence as real
    for domain in ('PRIVATE', 'FBA'):
        run_case(f'real persisted {domain} evidence and replay (TEST ONLY policy)', lambda db, m, p, s, seed, domain=domain: real.test_persisted_evidence_dispatch_and_replay(db, m, domain))
    for change in ('archive', 'metadata', 'permission', 'disabled', 'plan'):
        run_case(f'real evidence revoked: {change}', lambda db, m, p, s, seed, change=change: real.test_changes_revoke_persisted_authorization(db, m, change))
    run_case('generated BOL same transaction registers once', lambda db, m, p, s, seed: real.test_generated_bol_registration_same_transaction_is_idempotent(db, m))
    run_case('configured evidence requires locked plan', lambda db, m, p, s, seed: real.test_configured_policy_requires_final_plan(db, m))
    run_case('foreign warehouse exception blocks and redacts', lambda db, m, p, s, seed: real.test_foreign_warehouse_exception_blocks_without_disclosing_details(db, m))
    run_case('real review expiration', lambda db, m, p, s, seed: real.test_expired_review_blocks(db, m, p))
    run_case('real exception resolution attribution', lambda db, m, p, s, seed: real.test_active_exception_resolution_requires_attribution(db, m))
    run_case('real evidence dispatch rollback', lambda db, m, p, s, seed: real.test_real_evidence_dispatch_failure_rolls_back(db, m, p))
    def real_race(db, m, patch, sessions, seed):
        plan, doc = real.prepare(db, m); real.approve_all(db, m)
        actor_id, load_id = m.actor.id, m.load.id
        db.rollback(); barrier = Barrier(2)
        def dispatch(index):
            with sessions() as session:
                barrier.wait(timeout=15)
                gate.dispatch_load(session, session.get(User, actor_id), load_id, cases.request(plan, 'real-concurrent'))
        with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(dispatch, (1, 2)))
        assert db.query(LoadDispatchExecution).count() == 1
        review_id = db.query(real.DispatchEvidenceReview).first().id
        db.rollback()
        from sqlalchemy.exc import DBAPIError
        with sessions() as session:
            with pytest.raises(DBAPIError): session.execute(text('UPDATE dispatch_evidence_reviews SET note=:note WHERE id=:id'), {'note':'tamper','id':review_id})
            session.rollback()
        with sessions() as session:
            with pytest.raises(DBAPIError): session.execute(text('UPDATE dispatch_evidence_policies SET enabled=false'))
            session.rollback()
    run_case('real concurrent replay and database append-only enforcement', real_race)
    import test_dispatch_policy_config as policy_cases
    run_case('controlled policy dry-run, CAS publish, revoke and audit', lambda db, m, p, s, seed: policy_cases.test_preview_publish_revoke_and_audit(db, m))
    run_case('policy permission scope and injected publish rollback', lambda db, m, p, s, seed: policy_cases.test_scope_role_and_failed_publication_rollback(db, m, seed, p))
    def production_isolation(db, m, patch, sessions, seed):
        from app.core.config import settings
        from app.services import dispatch_policy_config as config, dispatch_evidence as evidence
        raw = policy_cases.draft(db, m)
        assert config.isolated_runtime(db)
        patch.setattr(settings, 'environment', 'production')
        assert not config.isolated_runtime(db)
        assert evidence.policy(db, m.load)[1] is None
        with pytest.raises(HTTPException): config.preview(db, m.actor, raw)
    run_case('actual PG application rejects TEST_ONLY under production environment', production_isolation)
    import test_migration_safety as partial_cases
    def partial_case(test):
        def body(db, m, patch, sessions, seed):
            client = conftest.client.__wrapped__(db, seed)
            try: test(client, db, seed)
            finally: client.close()
        return body
    run_case('partial completion concurrent quantities and duplicate rollback', partial_case(partial_cases.test_concurrent_partial_cannot_overdraw))
    run_case('partial completion retry overdraw rollback and full completion', partial_case(partial_cases.test_partial_retry_overdraw_then_full))
    run_case('operator credentials persisted role and inactive account', lambda db, m, p, s, seed: policy_cases.test_operator_requires_credentials_and_persisted_permission(db, m, seed))
    sys.path.insert(0, str(ROOT / 'scripts'))
    from verify_dispatch_upgrade import verify
    verify(admin, url, data, ROOT)
    admin.dispose()
    print(f'PASS isolated PostgreSQL: migration + {total} scenarios (policy success is test-only)', flush=True)


if __name__ == '__main__':
    worker(Path(sys.argv[2])) if len(sys.argv) == 3 and sys.argv[1] == '--worker' else parent()

