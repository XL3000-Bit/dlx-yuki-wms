"""Owned browser acceptance resources. Stop via the printed workspace/stop file.

Persisted TEST ONLY policies are seeded here, never in application startup.
No project credentials or database configuration are changed.
"""
import json
from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def seed(data):
    sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'backend/tests')]
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from alembic import command
    from alembic.config import Config
    import conftest
    import test_dispatch_lifecycle as cases
    from test_dispatch_evidence import install_test_policy
    from app.models import Warehouse, WarehouseArea, WarehouseLocation, InboundRecord, PickingList
    from app.models.operational_exception import OperationalException
    engine = create_engine(os.environ['DATABASE_URL'])
    with engine.connect() as c:
        assert Path(c.scalar(text('SHOW data_directory'))).resolve() == data.resolve()
        assert (data.parent / 'owned-by-dispatch-verification').read_text() == str(ROOT)
        assert c.scalar(text('SELECT current_user')) == 'codex_dispatch_test'
        c.rollback()
        cfg = Config(str(ROOT / 'backend/alembic.ini'))
        cfg.set_main_option('script_location', str(ROOT / 'backend/alembic'))
        cfg.attributes['connection'] = c
        command.upgrade(cfg, 'head')
    metadata = {}
    with Session(engine, expire_on_commit=False) as db:
        base = conftest.seed.__wrapped__(db)
        # Browser /users/me validates EmailStr, unlike direct service fixtures.
        for name in ('admin', 'viewer'):
            base[name].email = name + '@dispatch.example.com'
        db.commit()
        for domain in ('PRIVATE', 'FBA', 'UNCONFIGURED', 'EXPIRING'):
            local = dict(base)
            if domain in ('UNCONFIGURED', 'EXPIRING'):
                wh = Warehouse(warehouse_code=domain, warehouse_name='TEST ONLY ' + domain,
                               address='Test isolation', city='Test', state='CA', zip_code='00000')
                db.add(wh); db.commit(); local['warehouse'] = wh
                area = WarehouseArea(warehouse_id=wh.id, area_code='TEST', area_name='TEST ONLY')
                db.add(area); db.flush()
                location = WarehouseLocation(warehouse_id=wh.id, area_id=area.id,
                    location_code='TEST-STAGE', location_name='TEST ONLY staging')
                db.add(location); db.commit(); local['location'] = location
            m = cases.manifest.__wrapped__(db, local)
            inbound = db.get(InboundRecord, m.lot.source_inbound_id)
            inbound.inbound_no += '-' + domain; inbound.container_number += '-' + domain
            m.lot.lot_no += '-' + domain; m.lot.container_number = inbound.container_number
            m.load.load_no += '-' + domain; m.load.status = 'PLANNED'
            m.order.ob_no += '-' + domain
            db.get(PickingList, m.item.picking_list_id).picking_no += '-' + domain
            m.item.lot_no = m.lot.lot_no; m.item.container_number = inbound.container_number
            db.commit()
            if domain == 'FBA': m = cases.fba_manifest(db, m)
            if domain != 'UNCONFIGURED':
                install_test_policy(db, m, seconds=15 if domain == 'EXPIRING' else 3600,
                    documents=[{'document_type': 'BOL', 'scope': 'ORDER', 'allow_generated': True, 'bol_statuses': [1]},
                               {'document_type': 'WAREHOUSE', 'scope': 'LOAD', 'allow_generated': False, 'bol_statuses': []}])
            if domain in ('PRIVATE', 'FBA'):
                db.add(OperationalException(exception_no='TEST-EX-' + domain, title='TEST ONLY inspection needed',
                    warehouse_id=m.load.warehouse_id, load_id=m.load.id, reported_by=m.actor.id,
                    reported_at=datetime.now(timezone.utc),
                    exception_type='OUTBOUND', description='TEST ONLY browser acceptance'))
                db.commit()
            metadata[domain] = dict(load_id=m.load.id, order_id=m.order.id,
                                    picking_item_id=m.item.id, staging_location_id=m.location.id,
                                    allocation_id=m.inv.id, load_no=m.load.load_no,
                                    ob_no=m.order.ob_no, fba_id=m.order.fba_shipment_id)
    engine.dispose()
    (data.parent / 'fixtures.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    files = data.parent / 'upload-fixtures'; files.mkdir()
    for name, content in {'valid.csv': 'TEST ONLY evidence\nfixture,1\n', 'corrected.csv': 'TEST ONLY corrected evidence\nfixture,2\n',
                          'empty.csv': '', 'oversized.csv': 'x' * 5000}.items():
        (files / name).write_text(content, encoding='utf-8')


def main(resume=None):
    bins = Path(os.environ.get('YUKI_TEST_PG_BIN', r'C:\Program Files\PostgreSQL\17\bin'))
    workspace = Path(resume).resolve() if resume else Path(tempfile.mkdtemp(prefix='yuki-dispatch-browser-'))
    if resume:
        assert workspace.parent == Path(tempfile.gettempdir()).resolve()
        assert workspace.name.startswith('yuki-dispatch-browser-')
        assert (workspace / 'owned-by-dispatch-verification').read_text() == str(ROOT)
        assert (workspace / 'data/PG_VERSION').is_file()
        (workspace / 'stop').unlink(missing_ok=True)
    data = workspace / 'data'
    (workspace / 'owned-by-dispatch-verification').write_text(str(ROOT))
    pg, api, web = port(), port(), port()
    while len({pg, api, web}) != 3:
        pg, api, web = port(), port(), port()
    env = dict(os.environ, DATABASE_URL=f'postgresql+psycopg://codex_dispatch_test@127.0.0.1:{pg}/postgres',
               PYTHONUTF8='1', JWT_SECRET_KEY=secrets.token_urlsafe(48),
               DOCUMENT_STORAGE_ROOT=str(workspace / 'documents'), WMS_ENV='dispatch-isolated-test',
               DOCUMENT_MAX_UPLOAD_BYTES='4096',
               CORS_ORIGINS=json.dumps([f'http://127.0.0.1:{web}']), UNI_API_ORIGIN=f'http://127.0.0.1:{api}')
    (workspace / 'documents').mkdir(exist_ok=True)
    metadata = dict(workspace=str(workspace), postgres_port=pg, frontend=f'http://127.0.0.1:{web}', backend=f'http://127.0.0.1:{api}', policy='TEST ONLY mechanism validation; no production authorization')
    (workspace / 'resources.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(json.dumps(dict(metadata, phase='STARTING')), flush=True)
    children = []; handles = []; started = False
    def run(*args):
        with (workspace / 'cluster.log').open('a', encoding='utf-8') as log:
            subprocess.run([str(a) for a in args], stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW, check=True, timeout=120)
    try:
        if not resume: run(bins / 'initdb.exe', '-D', data, '-U', 'codex_dispatch_test', '-A', 'trust', '--encoding=UTF8', '--locale=C')
        run(bins / 'pg_ctl.exe', '-D', data, '-l', workspace / 'postgres.log', '-o', f'-h 127.0.0.1 -p {pg}', '-w', 'start')
        started = True
        if not resume:
            with (workspace / 'seed.log').open('w', encoding='utf-8') as log:
                result = subprocess.run([sys.executable, __file__, '--seed', str(data)], env=env, cwd=ROOT, stdout=log, stderr=log, timeout=90)
            if result.returncode: raise RuntimeError('Seed failed; inspect ' + str(workspace / 'seed.log'))
        commands = [([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(api)], ROOT / 'backend', 'backend.log'),
                    (['node', str(ROOT / 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', str(web), '--strictPort'], ROOT / 'frontend', 'frontend.log')]
        for args, cwd, logfile in commands:
            log = (workspace / logfile).open('a', encoding='utf-8'); handles.append(log)
            children.append(subprocess.Popen(args, cwd=cwd, env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW))
        for url in (f'http://127.0.0.1:{api}/openapi.json', f'http://127.0.0.1:{web}'):
            for attempt in range(60):
                if any(p.poll() is not None for p in children): raise RuntimeError('Test service exited; inspect owned logs')
                try:
                    with urllib.request.urlopen(url, timeout=1) as r: assert r.status == 200
                    break
                except Exception: time.sleep(0.5)
            else: raise RuntimeError('Test service readiness timeout')
        metadata = dict(workspace=str(workspace), postgres_port=pg, frontend=f'http://127.0.0.1:{web}', backend=f'http://127.0.0.1:{api}',
                        policy='TEST ONLY mechanism validation; no production authorization')
        (workspace / 'resources.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        print(json.dumps(metadata), flush=True)
        while not (workspace / 'stop').exists():
            if any(p.poll() is not None for p in children): raise RuntimeError('Test service exited')
            time.sleep(1)
    finally:
        try:
            for p in children:
                if p.poll() is None:
                    p.terminate()
                    try: p.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        p.kill(); p.wait(timeout=5)
        finally:
            for log in handles: log.close()
            if started: run(bins / 'pg_ctl.exe', '-D', data, '-m', 'fast', '-w', 'stop')
        print('Owned browser resources stopped; logs retained: ' + str(workspace), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--seed': seed(Path(sys.argv[2]))
    elif len(sys.argv) == 3 and sys.argv[1] == '--resume': main(sys.argv[2])
    elif len(sys.argv) == 1: main()
    else: raise SystemExit('Use no arguments or --resume <owned workspace>')
