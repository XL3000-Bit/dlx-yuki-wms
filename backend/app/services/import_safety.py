"""Transactional source identity and reversible, dependency-checked import journal.

The warehouse row serializes profile imports. Identity is retained in ImportRow,
independent of file names/hashes; canceled batches do not claim identities.
"""
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import event, inspect, select

from app.db.base import Base
from app.models import AuditLog, ImportJob, ImportRow, Warehouse
from app.models.import_job import ImportStatus, RowValidationStatus


def encode(value):
    if isinstance(value, dict): return {k: encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [encode(v) for v in value]
    if isinstance(value, Enum): return value.value
    if isinstance(value, (date, datetime)): return value.isoformat()
    if isinstance(value, Decimal): return str(value)
    return value


def identity(data, warehouse, profile):
    required = ('source_record_id', 'business_document_id', 'business_line_id', 'customer_id')
    missing = [key for key in required if not str(data.get(key) or '').strip()]
    if missing:
        raise HTTPException(422, {'code': 'SOURCE_IDENTITY_REQUIRED', 'fields': missing})
    prefix = [warehouse, profile]
    source = prefix + [str(data['source_record_id']).strip()]
    business = prefix + [data['customer_id'], str(data['business_document_id']).strip(), str(data['business_line_id']).strip()]
    # Parsed numerical representations are stable across XLSX/CSV formatting.
    canonical = {k: encode(v) for k, v in data.items() if k not in ('expected_revision', '_identity', '_previous_row_id')}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {'source': source, 'business': business, 'hash': digest}


def previous_rows(db, job):
    warehouse = int(job.options['warehouse_id'])
    db.scalar(select(Warehouse).where(Warehouse.id == warehouse).with_for_update())
    rows = db.scalars(select(ImportRow).join(ImportJob).where(
        ImportJob.profile_code == job.profile_code, ImportJob.status == ImportStatus.COMPLETED,
        ImportRow.validation_status == RowValidationStatus.IMPORTED).order_by(ImportRow.id)).all()
    sources, businesses = {}, {}
    for row in rows:
        marker = (row.mapped_data or {}).get('_identity')
        if not marker:
            prior_job = db.get(ImportJob, row.import_job_id)
            if int((prior_job.options or {}).get('warehouse_id') or 0) in (0, warehouse):
                raise HTTPException(409, {'code': 'LEGACY_IDENTITY_RECONCILIATION_REQUIRED',
                                         'job_id': prior_job.id, 'row_id': row.id,
                                         'reason': 'Prior imported row has no stable identity; reconcile before importing'})
            continue
        if marker['source'][0] != warehouse: continue
        sources[tuple(marker['source'])] = row
        businesses[tuple(marker['business'])] = row
    return sources, businesses


def check_row(data, job, sources, businesses, strategy):
    marker = identity(data, int(job.options['warehouse_id']), job.profile_code)
    old = sources.get(tuple(marker['source']))
    same_business = businesses.get(tuple(marker['business']))
    if same_business and (same_business.mapped_data['_identity']['source'] != marker['source']):
        raise HTTPException(409, 'BUSINESS_KEY_CONFLICT: different source ID claims the same document/detail')
    if old:
        prior = old.mapped_data['_identity']
        if marker['business'] != prior['business']:
            raise HTTPException(409, 'SOURCE_KEY_CONFLICT: owner/document/detail changed')
        if marker['hash'] == prior['hash']: return dict(prior), old, True
        if strategy != 'UPDATE': raise HTTPException(409, 'SOURCE_CHANGED: use UPDATE with expected_revision')
        if str(data.get('expected_revision') or '') != str(prior['revision']):
            raise HTTPException(409, 'STALE_REVISION: refresh source revision before update')
    marker['revision'] = (old.mapped_data['_identity']['revision'] if old else 0) + 1
    return marker, old, False


EXCLUDED = {'import_jobs', 'import_rows', 'import_errors', 'audit_logs'}


class BatchJournal:
    def __init__(self, db):
        self.db, self.objects = db, {}
        event.listen(db, 'before_flush', self.capture)

    def capture(self, session, *_):
        for obj in list(session.new) + list(session.dirty) + list(session.deleted):
            state = inspect(obj)
            table = state.mapper.local_table
            if table.name in EXCLUDED or not hasattr(obj, 'id'): continue
            if id(obj) in self.objects: continue
            before = None
            if state.identity:
                row = session.connection().execute(select(table).where(table.c.id == obj.id)).mappings().first()
                before = encode(dict(row)) if row else None
            self.objects[id(obj)] = (obj, table, before)

    def finish(self):
        self.db.flush()
        changes = []
        for obj, table, before in self.objects.values():
            row = self.db.connection().execute(select(table).where(table.c.id == obj.id)).mappings().first()
            after = encode(dict(row)) if row else None
            if before != after:
                changes.append({'table': table.name, 'id': obj.id, 'before': before, 'after': after,
                                'dependencies': dependencies(self.db, table, obj.id)})
        return {'version': 1, 'changes': changes}

    def close(self):
        event.remove(self.db, 'before_flush', self.capture)


def dependencies(db, parent, record_id):
    result = {}
    for table in Base.metadata.tables.values():
        if table.name in EXCLUDED or 'id' not in table.c: continue
        for fk in table.foreign_keys:
            if fk.column.table is parent and fk.column.name == 'id':
                result[f'{table.name}.{fk.parent.name}'] = sorted(db.scalars(
                    select(table.c.id).where(fk.parent == record_id)).all())
    # Audit IDs are scoped by entity type; numeric IDs overlap between tables.
    entity_types = {'inbound_records': 'INBOUND', 'inventory_lots': 'INVENTORY',
                    'outbound_orders': 'OUTBOUND', 'warehouse_locations': 'LOCATION',
                    'fba_shipments': 'FBA'}
    kind = entity_types.get(parent.name)
    result['_audit'] = sorted(db.scalars(select(AuditLog.id).where(
        AuditLog.entity_type == kind, AuditLog.entity_id == record_id)).all()) if kind else []
    return result


def decode_row(table, values):
    result = {}
    for key, value in values.items():
        if value is not None:
            typ = table.c[key].type
            try: python_type = typ.python_type
            except (NotImplementedError, AttributeError): python_type = None
            if python_type is datetime: value = datetime.fromisoformat(value)
            elif python_type is date: value = date.fromisoformat(value)
            elif python_type is Decimal: value = Decimal(value)
        result[key] = value
    return result


def rollback_batch(db, job_id, user):
    from app.services.access_policy import assert_warehouse_access, assert_customer_access
    job = db.get(ImportJob, job_id)
    if not job: raise HTTPException(404, 'Import batch not found')
    warehouse = int((job.options or {}).get('warehouse_id') or 0)
    assert_warehouse_access(user, warehouse)
    db.scalar(select(Warehouse).where(Warehouse.id == warehouse).with_for_update())
    job = db.scalar(select(ImportJob).where(ImportJob.id == job_id).with_for_update().execution_options(populate_existing=True))
    journal = (job.options or {}).get('migration_journal')
    if job.status != ImportStatus.COMPLETED or not journal:
        raise HTTPException(409, 'BATCH_NOT_REVERSIBLE: missing journal or batch already rolled back')
    changes = journal['changes']; blockers = []
    # Lock in deterministic table/ID order, then re-read. No changes until every
    # after-image and every incoming dependency has been verified.
    for change in sorted(changes, key=lambda c: (c['table'], c['id'])):
        table = Base.metadata.tables[change['table']]
        row = db.execute(select(table).where(table.c.id == change['id']).with_for_update()).mappings().first()
        current = encode(dict(row)) if row else None
        if current and 'customer_id' in current: assert_customer_access(user, current['customer_id'])
        if current != change['after']:
            blockers.append(f"{table.name}#{change['id']}: changed after import")
        if dependencies(db, table, change['id']) != change['dependencies']:
            blockers.append(f"{table.name}#{change['id']}: subsequent business/audit dependency")
    # Later imports may reuse an entity without changing its business fields.
    ids = {row.id for row in db.scalars(select(ImportRow).where(ImportRow.import_job_id == job.id))}
    for row in db.scalars(select(ImportRow).join(ImportJob).where(ImportJob.status == ImportStatus.COMPLETED, ImportJob.id != job.id)):
        if (row.mapped_data or {}).get('_previous_row_id') in ids:
            blockers.append(f'Import batch {row.import_job_id} depends on this batch')
    if blockers: raise HTTPException(409, {'code': 'ROLLBACK_DEPENDENCY', 'reasons': blockers})
    ordering = {table.name: index for index, table in enumerate(Base.metadata.sorted_tables)}
    for change in sorted(changes, key=lambda c: ordering[c['table']], reverse=True):
        table = Base.metadata.tables[change['table']]
        if change['before'] is None: db.execute(table.delete().where(table.c.id == change['id']))
        else: db.execute(table.update().where(table.c.id == change['id']).values(**decode_row(table, change['before'])))
    job.status = ImportStatus.CANCELED; job.current_stage = 'ROLLED_BACK'
    db.add(AuditLog(user_id=user.id, action='ROLLBACK_IMPORT_BATCH', entity_type='IMPORT_JOB', entity_id=job.id,
                    after_data={'reversed_changes': len(changes)}))
    db.commit(); db.expire_all()
    return {'job_id': job_id, 'status': 'ROLLED_BACK', 'reversed_changes': len(changes)}
