"""Owned-cluster upgrade, failure recovery and backup proof; called by isolated verifier."""
from pathlib import Path
import os
import subprocess
from datetime import datetime, timezone


def verify(admin, url, data, root):
    from sqlalchemy import create_engine, text, MetaData, Table, event, inspect
    from sqlalchemy.exc import DBAPIError
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.orm import Session
    from fastapi import HTTPException
    from app.models import User
    from app.services import dispatch_policy_config as policies

    assert data.parent.joinpath('owned-by-dispatch-verification').read_text(encoding='utf-8') == str(root)
    with admin.connect() as conn:
        conn.execute(text('CREATE DATABASE dispatch_upgrade'))
    engine = create_engine(url.rsplit('/', 1)[0] + '/dispatch_upgrade')
    cfg = Config(str(root / 'backend/alembic.ini'))
    cfg.set_main_option('script_location', str(root / 'backend/alembic'))
    def upgrade(target):
        with engine.connect() as conn:
            cfg.attributes['connection'] = conn
            command.upgrade(cfg, target)
    upgrade('20260917_0036')
    metadata = MetaData()
    tables = {name: Table(name, metadata, autoload_with=engine) for name in
              ('users', 'warehouses', 'customers', 'loads', 'outbound_orders', 'operational_documents')}
    now = datetime.now(timezone.utc)
    def insert(conn, name, **values):
        table = tables[name]
        for stamp in ('created_at', 'updated_at'):
            if stamp in table.c: values[stamp] = now
        conn.execute(table.insert().values(**values))
    with engine.begin() as conn:
        for uid, role in ((1, 'ADMIN'), (2, 'VIEWER')):
            insert(conn, 'users', id=uid, username=f'TEST-UPGRADE-{role}', display_name=f'TEST ONLY {role}',
                   email=f'test-upgrade-{uid}@example.invalid', password_hash='TEST_ONLY_UNUSABLE_HASH', role=role,
                   warehouse_scope_mode='ALL', customer_scope_mode='ALL')
        insert(conn, 'warehouses', id=1, warehouse_code='TEST-UPGRADE', warehouse_name='TEST ONLY upgrade',
               address='TEST ONLY', city='TEST ONLY', state='TEST ONLY', zip_code='00000')
        insert(conn, 'customers', id=1, customer_code='TEST-UPGRADE', customer_name='TEST ONLY upgrade')
        insert(conn, 'loads', id=1, load_no='TEST-LEGACY-UNKNOWN', warehouse_id=1, created_by=1, status='PLANNED')
        insert(conn, 'outbound_orders', id=1, ob_no='TEST-LEGACY-UNKNOWN', warehouse_id=1, customer_id=1,
               created_by=1, status=0, notify_carrier=False, ob_type='STANDARD', load_id=1)
        for did in (1, 2):
            insert(conn, 'operational_documents', id=did, document_no=f'TEST-LEGACY-DUP-{did}',
                   document_type='WAREHOUSE', status='AVAILABLE', version=1, original_filename='TEST_ONLY.csv',
                   content_type='text/csv', file_size=1, is_generated=False, warehouse_id=1,
                   customer_id=1, load_id=1, created_by=1)
    print('PASS representative 0036 data: explicit TEST identities and duplicate legacy documents', flush=True)
    bins = Path(os.environ.get('YUKI_TEST_PG_BIN', r'C:\Program Files\PostgreSQL\17\bin'))
    port = engine.url.port
    backup = data.parent / 'pre0037.dump'
    def pg(command_name, *args):
        with (data.parent / 'backup-restore.log').open('a', encoding='utf-8') as log:
            result = subprocess.run([str(bins / command_name), '-h', '127.0.0.1', '-p', str(port),
                                     '-U', 'codex_dispatch_test', *map(str, args)], stdout=log, stderr=log,
                                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=120)
        assert result.returncode == 0, 'Owned backup/restore failed; inspect retained log'
    pg('pg_dump.exe', '-Fc', '-f', backup, 'dispatch_upgrade')
    with admin.connect() as conn: conn.execute(text('CREATE DATABASE dispatch_upgrade_restore'))
    pg('pg_restore.exe', '--exit-on-error', '-d', 'dispatch_upgrade_restore', backup)
    restored = create_engine(url.rsplit('/', 1)[0] + '/dispatch_upgrade_restore')
    with restored.connect() as conn:
        assert conn.scalar(text('SELECT version_num FROM alembic_version')) == '20260917_0036'
        assert conn.scalar(text('SELECT count(*) FROM operational_documents')) == 2
    restored.dispose()
    print('PASS pre-upgrade pg_dump and pg_restore to separate owned database', flush=True)
    upgrade('20261005_0038')
    def fail(conn, cursor, statement, parameters, context, executemany):
        if 'CREATE FUNCTION dispatch_evidence_source_lock' in statement:
            raise RuntimeError('TEST ONLY injected migration failure')
    event.listen(engine, 'before_cursor_execute', fail)
    try:
        try: upgrade('20261005_0039')
        except RuntimeError: pass
        else: raise AssertionError('Injected migration did not fail')
    finally: event.remove(engine, 'before_cursor_execute', fail)
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT version_num FROM alembic_version')) == '20261005_0038'
        assert 'dispatch_evidence_policies' not in inspect(conn).get_table_names()
        assert 'dispatch_business_type' not in {col['name'] for col in inspect(conn).get_columns('operational_documents')}
        assert conn.scalar(text('SELECT count(*) FROM operational_documents')) == 2
    print('PASS failed 0039 migration rolls back schema/version/data; no cleanup', flush=True)
    upgrade('head')
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT version_num FROM alembic_version')) == '20261005_0039'
        for name in ('loads', 'outbound_orders', 'operational_documents'):
            assert conn.scalar(text(f'SELECT count(*) FROM {name} WHERE dispatch_business_type IS NOT NULL')) == 0
        assert conn.scalar(text('SELECT count(*) FROM operational_documents WHERE version=1')) == 2
        assert conn.scalar(text('SELECT count(*) FROM dispatch_evidence_reviews')) == 0
        assert conn.scalar(text('SELECT count(*) FROM dispatch_evidence_policies')) == 0
    with engine.begin() as conn:
        try:
            with conn.begin_nested(): conn.execute(text("UPDATE operational_documents SET dispatch_business_type='GUESS'"))
        except DBAPIError: pass
        else: raise AssertionError('Invalid document business accepted')
    with Session(engine) as db:
        assert policies.source_allowed(db, 'TEST_ONLY legacy string') is False
        assert policies.isolated_runtime(db) is True
        from app.services.load_dispatch_gate import integrated_readiness
        readiness = integrated_readiness(db, db.get(User, 1), 1)
        assert not readiness.ready
        from app.services.load_dispatch_write import validate_business
        from app.models import Load
        try: validate_business(db.get(Load, 1), [])
        except HTTPException as error: assert 'DISPATCH_BUSINESS_TYPE_MISSING' in str(error.detail)
        else: raise AssertionError('Historical UNKNOWN business accepted')
        assert db.execute(text('SELECT status FROM loads WHERE id=1')).scalar() != 'DISPATCHED'
        raw = dict(warehouse_id=1, business_type='PRIVATE', expected_version=0,
            provenance=dict(purpose='TEST_ONLY', confirmation_reference='TEST ONLY upgrade permission check',
                rule_sources={key: 'TEST ONLY upgrade fixture' for key in policies.SOURCE_FIELDS}),
            rules=dict(documents=[dict(document_type='WAREHOUSE', scope='LOAD', allow_generated=False, bol_statuses=[])],
                document_review=dict(roles=['ADMIN'], valid_seconds=60), approval=dict(roles=['ADMIN'], valid_seconds=60),
                exception_review=dict(roles=['ADMIN'], valid_seconds=60), independent_approver=False,
                allow_canceled_exceptions=False))
        try: policies.preview(db, db.get(User, 2), raw)
        except HTTPException as error: assert error.status_code == 403
        else: raise AssertionError('Viewer configuration permission bypass')
    engine.dispose()
    print('PASS 0037..0039 retry preserves UNKNOWN, duplicates and identities; constraints and viewer denial', flush=True)
