"""Controlled operator tool; template/validate do not open a database.

Use backend/.venv/Scripts/python.exe scripts/dispatch_policy.py --help.
No command imports test seeds. Publication requires a complete confirmed draft.
"""
import argparse
import getpass
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['template', 'validate', 'dry-run', 'publish', 'revoke'])
    parser.add_argument('--business', choices=['FBA', 'PRIVATE'])
    parser.add_argument('--file', type=Path)
    parser.add_argument('--username', help='Active operator account; role and warehouse scope are checked')
    parser.add_argument('--password-stdin', action='store_true', help='Read one password line from stdin; never pass passwords as arguments')
    args = parser.parse_args()
    from app.services.dispatch_policy_config import template, PolicyDraft, preview, publish
    if args.command == 'template':
        if not args.business: parser.error('--business is required')
        print(json.dumps(template(args.business), ensure_ascii=False, indent=2)); return
    if not args.file: parser.error('--file is required')
    raw = json.loads(args.file.read_text(encoding='utf-8-sig'))
    if args.command == 'validate':
        PolicyDraft.model_validate(raw)
        print('Valid complete draft; no database access or business authorization granted'); return
    if not args.username: parser.error('--username is required')
    password = sys.stdin.readline().rstrip('\r\n') if args.password_stdin else getpass.getpass('Operator password: ')
    if not password: parser.error('Operator password is required')
    from app.db.session import SessionLocal
    from app.services.dispatch_policy_config import authenticate_operator
    with SessionLocal() as db:
        actor = authenticate_operator(db, args.username, password)
        if args.command == 'dry-run': result = preview(db, actor, raw)[1]
        else: result = publish(db, actor, raw, revoke=args.command == 'revoke')
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    from fastapi import HTTPException
    from pydantic import ValidationError
    from sqlalchemy.exc import SQLAlchemyError
    try:
        main()
    except ValidationError as error:
        # Field paths are useful for incomplete drafts; never echo input values.
        print(json.dumps({'pending_or_invalid_fields': [
            {'field': '.'.join(map(str, item['loc'])), 'reason': item['msg']}
            for item in error.errors(include_input=False)]}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
    except HTTPException as error:
        print(json.dumps({'status': error.status_code, 'reason': error.detail}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
    except (OSError, json.JSONDecodeError):
        print('Draft file cannot be read or is not valid JSON', file=sys.stderr)
        raise SystemExit(2)
    except SQLAlchemyError:
        print('Database operation failed and was not published; inspect restricted operator logs', file=sys.stderr)
        raise SystemExit(2)
