"""Rehearse recovery and authenticated policy operations in NEW owned databases.

Requires a live start_dispatch_browser_isolated.py workspace. The source is only
dumped; all publication and fault injection happen in a newly created clone.
Passwords remain local, are sent via stdin, and are never included in reports.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import psycopg
from psycopg import sql


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    workspace = args.workspace.resolve()
    assert workspace.name.startswith('yuki-dispatch-browser-')
    assert (workspace / 'owned-by-dispatch-verification').read_text() == str(ROOT)
    meta = json.loads((workspace / 'resources.json').read_text())
    port = int(meta['postgres_port'])
    conninfo = dict(host='127.0.0.1', port=port, user='codex_dispatch_test', dbname='postgres')
    with psycopg.connect(**conninfo, autocommit=True) as c:
        assert Path(c.execute('SHOW data_directory').fetchone()[0]).resolve() == workspace / 'data'
        assert c.execute('SELECT current_user').fetchone()[0] == 'codex_dispatch_test'
    work = workspace / ('release-rehearsal-' + uuid.uuid4().hex[:12])
    work.mkdir()
    args.output.mkdir(parents=True, exist_ok=True)
    bins = Path(os.environ.get('YUKI_TEST_PG_BIN', r'C:\Program Files\PostgreSQL\17\bin'))
    pgargs = ['-h', '127.0.0.1', '-p', str(port), '-U', 'codex_dispatch_test']
    results = []
    def passed(name, **details):
        results.append(dict(name=name, status='PASS', **details))
    def run(command):
        with (work / 'operations.log').open('a', encoding='utf-8') as log:
            subprocess.run([str(x) for x in command], check=True, stdout=log, stderr=log,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=120)
    def snapshot(database):
        with psycopg.connect(**dict(conninfo, dbname=database)) as c:
            names = [r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
            result = {}
            for name in names:
                rows = c.execute(sql.SQL('SELECT row_to_json(t)::text FROM {} t').format(sql.Identifier(name))).fetchall()
                normalized = sorted(json.dumps(json.loads(r[0]), sort_keys=True, ensure_ascii=False) for r in rows)
                result[name] = dict(rows=len(rows), sha256=hashlib.sha256('\n'.join(normalized).encode()).hexdigest())
            return result
    def files(directory):
        return {str(f.relative_to(directory)): hashlib.sha256(f.read_bytes()).hexdigest()
                for f in sorted(directory.rglob('*')) if f.is_file()}
    before = snapshot('postgres')
    dump = work / 'database.dump'
    run([bins / 'pg_dump.exe', *pgargs, '-Fc', '-f', dump, 'postgres'])
    clones = ['dispatch_rehearsal_' + uuid.uuid4().hex[:12] for _ in range(2)]
    for clone in clones:
        with psycopg.connect(**conninfo, autocommit=True) as c:
            c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(clone)))
        run([bins / 'pg_restore.exe', *pgargs, '--exit-on-error', '-d', clone, dump])
        assert snapshot(clone) == before
    passed('database_backup_restore_twice', tables=len(before), backup_sha256=hashlib.sha256(dump.read_bytes()).hexdigest(), snapshots=before)
    backup_files = work / 'file-backup'
    restored_files = work / 'file-restored'
    shutil.copytree(workspace / 'documents', backup_files)
    shutil.copytree(backup_files, restored_files)
    file_manifest = files(workspace / 'documents')
    assert file_manifest and file_manifest == files(backup_files) == files(restored_files)
    passed('file_storage_restore', files=len(file_manifest), manifest=file_manifest)
    with psycopg.connect(**dict(conninfo, dbname=clones[1])) as c:
        stored = c.execute('SELECT id, storage_key, file_size, checksum_sha256 FROM operational_documents WHERE storage_key IS NOT NULL').fetchall()
        for document_id, key, size, checksum in stored:
            target = (restored_files / key).resolve()
            assert restored_files.resolve() in target.parents
            assert target.is_file() and target.stat().st_size == size, document_id
            assert hashlib.sha256(target.read_bytes()).hexdigest() == checksum, document_id
    passed('restored_document_rows_match_files', documents=len(stored))
    database = clones[0]
    env = dict(os.environ, DATABASE_URL=f'postgresql+psycopg://codex_dispatch_test@127.0.0.1:{port}/{database}',
               WMS_ENV='dispatch-isolated-test', PYTHONUTF8='1', DOCUMENT_STORAGE_ROOT=str(restored_files))
    def cli(command, draft, username='admin', environment=None, wrong=False):
        path = work / 'draft.json'
        path.write_text(json.dumps(draft), encoding='utf-8')
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/dispatch_policy.py'), command,
                                '--file', str(path), '--username', username, '--password-stdin'],
                                input=('incorrect' if wrong else 'WarehousePassword!') + '\n',
                                text=True, capture_output=True, env=environment or env, cwd=ROOT, timeout=60,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        return result.returncode, result.stdout, result.stderr
    for business in ('PRIVATE', 'FBA'):
        with psycopg.connect(**dict(conninfo, dbname=database)) as c:
            warehouse, version, source, rules = c.execute("SELECT warehouse_id, version, source, rules FROM dispatch_evidence_policies WHERE business_type=%s AND warehouse_id=1 ORDER BY version DESC LIMIT 1", (business,)).fetchone()
        draft = dict(warehouse_id=warehouse, business_type=business, expected_version=version,
                     provenance=json.loads(source), rules=rules)
        draft['rules']['document_review']['valid_seconds'] = 7200
        stable = snapshot(database)
        for name, user, wrong, environment, code in [
            ('wrong_password', 'admin', True, env, 401),
            ('viewer_permission', 'viewer', False, env, 403),
            ('production_rejects_test_policy', 'admin', False, dict(env, WMS_ENV='production'), 409)]:
            rc, out, err = cli('dry-run', draft, user, environment, wrong)
            assert rc == 2 and json.loads(err)['status'] == code, (name, rc, err)
            assert snapshot(database) == stable
            passed(business + '_' + name, response=code)
        rc, out, err = cli('dry-run', draft)
        assert rc == 0, err
        diff = json.loads(out)
        assert diff['differences']['document_review']['after']['valid_seconds'] == 7200
        assert snapshot(database) == stable
        passed(business + '_dry_run_diff_no_writes', differences=diff['differences'])
        with psycopg.connect(**dict(conninfo, dbname=database), autocommit=True) as c:
            c.execute("CREATE FUNCTION rehearsal_fail_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'TEST ONLY injected publication failure'; END $$")
            c.execute('CREATE TRIGGER rehearsal_fail_audit BEFORE INSERT ON audit_logs FOR EACH ROW EXECUTE FUNCTION rehearsal_fail_audit()')
        rc, out, err = cli('publish', draft)
        assert rc == 2 and 'not published' in err
        assert snapshot(database) == stable
        passed(business + '_publication_failure_atomic_rollback')
        with psycopg.connect(**dict(conninfo, dbname=database), autocommit=True) as c:
            c.execute('DROP TRIGGER rehearsal_fail_audit ON audit_logs')
            c.execute('DROP FUNCTION rehearsal_fail_audit()')
        rc, out, err = cli('publish', draft)
        assert rc == 0 and json.loads(out)['version'] == version + 1, err
        published = snapshot(database)
        rc, out, err = cli('publish', draft)
        assert rc == 2 and json.loads(err)['status'] == 409
        assert snapshot(database) == published
        draft['expected_version'] = version + 1
        rc, out, err = cli('revoke', draft)
        assert rc == 0 and json.loads(out)['enabled'] is False, err
        draft['expected_version'] = version + 2
        rc, out, err = cli('publish', draft)
        assert rc == 0 and json.loads(out)['enabled'] is True, err
        with psycopg.connect(**dict(conninfo, dbname=database)) as c:
            count = c.execute('SELECT count(*) FROM dispatch_evidence_policies WHERE warehouse_id=1 AND business_type=%s', (business,)).fetchone()[0]
            actions = c.execute("SELECT action FROM audit_logs WHERE entity_type='dispatch_evidence_policy' AND after_data->>'business_type'=%s ORDER BY id", (business,)).fetchall()
            assert count == 4 and [r[0] for r in actions[-3:]] == ['PUBLISH', 'REVOKE', 'PUBLISH']
        passed(business + '_publish_stale_revoke_recover_history', versions_preserved=count, actions=['PUBLISH', 'REVOKE', 'PUBLISH'])
    assert snapshot('postgres') == before
    assert snapshot(clones[1]) == before
    assert files(workspace / 'documents') == file_manifest
    passed('source_unchanged_and_recovery_clone_preserved')
    report = dict(status='COMPLETE_TEST_ONLY', production_ready=False, workspace=str(work), databases=clones,
                  results=results, policy='TEST ONLY mechanism rehearsal; no production authorization')
    (args.output / 'release-rehearsal.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(status=report['status'], passed=len(results), workspace=str(work))))


if __name__ == '__main__':
    main()
