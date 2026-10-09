"""One-command formal-page acceptance. Owns only resources created by its launcher.

Run with backend/.venv/Scripts/python.exe scripts/verify_dispatch_ui.py.
No user Chrome, production database, API business writes or saved authentication state.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def stamp():
    return datetime.now(timezone.utc).isoformat()

def owned(workspace):
    import tempfile
    p = Path(workspace).resolve()
    assert p.parent == Path(tempfile.gettempdir()).resolve()
    assert p.name.startswith('yuki-dispatch-browser-')
    assert (p / 'owned-by-dispatch-verification').read_text() == str(ROOT)
    return p

def fault(workspace, action):
    """Explicit isolated fault injection, never a replacement for page operations."""
    p = owned(workspace)
    resources = json.loads((p / 'resources.json').read_text())
    if action in ('storage-block', 'storage-restore'):
        root, saved = p / 'documents', p / 'documents-fault-backup'
        if action == 'storage-block':
            assert root.is_dir() and not saved.exists()
            root.rename(saved)
            root.write_text('TEST ONLY simulated storage outage', encoding='utf-8')
        else:
            assert root.is_file() and saved.is_dir()
            root.unlink()
            saved.rename(root)
    else:
        from sqlalchemy import create_engine, text
        engine = create_engine(f"postgresql+psycopg://codex_dispatch_test@127.0.0.1:{resources['postgres_port']}/postgres")
        with engine.begin() as c:
            assert Path(c.scalar(text('SHOW data_directory'))).resolve() == p / 'data'
            assert c.scalar(text('SELECT current_user')) == 'codex_dispatch_test'
            # Real role revocation/restoration for the seeded test administrator;
            # browser still submits its cached form, server must recheck authority.
            role = 'VIEWER' if action == 'role-revoke' else 'ADMIN'
            result = c.execute(text("UPDATE users SET role=:role WHERE username='admin'"), {'role': role})
            assert result.rowcount == 1
        engine.dispose()
    print(json.dumps({'fault': action, 'isolation_verified': True}))

def main(output=None, grep=None):
    destination = Path(output).resolve() if output else ROOT / 'docs/evidence' / ('dispatch-playwright-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    destination.mkdir(parents=True, exist_ok=False)
    manifest = {'started_at': stamp(), 'production_ready': False,
                'policy': 'TEST ONLY isolated mechanism validation; not approved production rules',
                'file_input': 'Playwright setInputFiles in exclusive browser',
                'native_file_picker': 'NOT_VERIFIED', 'existing_chrome_upload': 'BLOCKED_PREVIOUSLY_NOT_RETRIED',
                'code_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'worktree_summary': subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True),
                'cleanup': {'status': 'NOT_STARTED'}}
    lines = queue.Queue()
    process = subprocess.Popen([sys.executable, '-u', str(ROOT / 'scripts/start_dispatch_browser_isolated.py')],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env={**os.environ, 'PYTHONUTF8': '1'}, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
    def drain(stream, path, ready=False):
        with path.open('w', encoding='utf-8') as log:
            for line in stream:
                log.write(line); log.flush()
                if ready: lines.put(line)
    readers = [threading.Thread(target=drain, args=(process.stdout, destination / 'launcher.log', True), daemon=True),
               threading.Thread(target=drain, args=(process.stderr, destination / 'launcher-errors.log'), daemon=True)]
    for reader in readers: reader.start()
    workspace = None
    status = 1
    ready = False
    browser = None
    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if process.poll() is not None: raise RuntimeError('Isolated launcher exited; inspect launcher logs')
            try: line = lines.get(timeout=1)
            except queue.Empty: continue
            if line.startswith('{'):
                metadata = json.loads(line)
                workspace = owned(metadata['workspace'])
                if metadata.get('phase') != 'STARTING':
                    ready = True
                    break
        if not ready: raise RuntimeError('Isolated startup timeout')
        manifest['resources'] = metadata
        env = {**os.environ, 'YUKI_UI_BASE': metadata['frontend'], 'YUKI_UI_WORKSPACE': str(workspace),
               'YUKI_UI_EVIDENCE': str(destination), 'YUKI_UI_PYTHON': sys.executable,
               'YUKI_UI_RUNNER': str(Path(__file__).resolve())}
        command = ['node', str(ROOT / 'frontend/node_modules/@playwright/test/cli.js'), 'test', '--config=playwright.dispatch.config.ts']
        if grep: command += ['--grep', grep]
        browser = subprocess.Popen(command, cwd=ROOT / 'frontend', env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        with (destination / 'browser.log').open('w', encoding='utf-8') as log:
            for line in browser.stdout:
                log.write(line); log.flush()
                print(line, end='', flush=True)
        status = browser.wait()
        manifest['browser_exit_code'] = status
    except Exception as e:
        manifest['error'] = str(e)
    finally:
        if browser is not None and browser.poll() is None:
            browser.terminate()
            try: browser.wait(timeout=10)
            except subprocess.TimeoutExpired:
                browser.kill()
                browser.wait(timeout=5)
            manifest['interrupted_browser_exit_code'] = browser.returncode
        if workspace:
            # Restore an interrupted fault before stopping owned processes.
            if (workspace / 'documents-fault-backup').is_dir():
                try: fault(str(workspace), 'storage-restore')
                except Exception as e: manifest['fault_restore_error'] = str(e)
            (workspace / 'stop').write_text('stop owned resources', encoding='utf-8')
            try: process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                manifest['cleanup'] = {'status': 'FAILED', 'reason': 'Owned launcher did not stop within 45 seconds'}
            else:
                ports = [metadata['postgres_port']] + [int(metadata[k].rsplit(':', 1)[1]) for k in ('frontend', 'backend')]
                listening = []
                for port in ports:
                    with socket.socket() as s:
                        if s.connect_ex(('127.0.0.1', port)) == 0: listening.append(port)
                manifest['cleanup'] = {'status': 'PASS' if not listening and process.returncode == 0 else 'FAILED',
                                       'launcher_exit_code': process.returncode, 'remaining_listeners': listening,
                                       'workspace_retained': str(workspace)}
            for name in ('cluster.log', 'postgres.log', 'seed.log', 'backend.log', 'frontend.log', 'fixtures.json'):
                if (workspace / name).is_file(): shutil.copy2(workspace / name, destination / name)
        elif process.poll() is None:
            # Launcher startup is bounded. Allow its own finally to stop its cluster.
            for _ in range(5):
                try: process.wait(timeout=30); break
                except subprocess.TimeoutExpired: pass
            if process.poll() is None:
                manifest['cleanup'] = {'status': 'UNKNOWN', 'reason': 'Startup still active; inspect launcher log'}
        for reader in readers: reader.join(timeout=5)
        manifest['finished_at'] = stamp()
        manifest['worktree_summary_after'] = subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True)
        manifest['tracked_diff_summary'] = subprocess.check_output(['git', 'diff', '--stat'], cwd=ROOT, text=True)
        page_results = destination / 'page-results.json'
        checks = json.loads(page_results.read_text(encoding='utf-8')) if page_results.is_file() else {'steps': []}
        checks.update({'started_at': manifest['started_at'], 'finished_at': manifest['finished_at'],
                       'production_ready': False, 'mechanism_acceptance_complete': False,
                       'browser_exit_code': status, 'cleanup': manifest['cleanup'],
                       'existing_chrome_upload': manifest['existing_chrome_upload'],
                       'native_file_picker': 'NOT_VERIFIED',
                       'summary': {state: sum(s.get('status') == state for s in checks['steps']) for state in ('PASS', 'FAIL', 'SKIP', 'RUNNING')}})
        (destination / 'results.json').write_text(json.dumps(checks, indent=2, ensure_ascii=False), encoding='utf-8')
        (destination / 'run.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'Acceptance evidence: {destination}')
        print(f"Owned resource cleanup: {manifest['cleanup']['status']}")
    return status if manifest['cleanup']['status'] == 'PASS' else 1

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output')
    parser.add_argument('--grep')
    parser.add_argument('--fault', choices=['storage-block', 'storage-restore', 'role-revoke', 'role-restore'])
    parser.add_argument('--workspace')
    args = parser.parse_args()
    if args.fault:
        fault(args.workspace, args.fault)
    else:
        raise SystemExit(main(args.output, args.grep))
