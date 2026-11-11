"""Export everything VietBiz holds for one company (GDPR art. 20 portability, and a clean
hand-over when a business changes accountant or leaves VietBiz).

`GET /v1/organizations/{org}/export` — owner only — answers a ZIP with:

- `README.txt`: what is inside, when it was made, and any original that could not be opened;
- `data/<table>.json`: every row of the company in each table, without internal fields
  (idempotency keys, request hashes, server file paths);
- `originals/documents/…` and `originals/statements/…`: the uploaded files, decrypted.

Accountant-only notes on tasks (`visibility = 'accountant'`) are the accounting firm's own
working notes and are left out of the owner's export. Every export is written to the audit log.
"""
from __future__ import annotations

import io
import json
import re
import tempfile
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from .crypto import document_context, statement_context, unseal
from .database import connection
from .web_security import attachment_disposition

# Tables that belong to one company, with the columns that stay inside VietBiz.
TABLES = {
    'organizations': (),
    'memberships': (),
    'invitations': (),
    'billing_profiles': (),
    'client_profiles': (),
    'documents': ('storage_path',),
    'document_extractions': (),
    'document_flags': (),
    'document_line_sets': (),
    'document_lines': (),
    'goods_catalogue': (),
    'accounting_tasks': ('idempotency_key', 'request_hash'),
    'task_events': (),
    'task_comments': ('idempotency_key', 'request_hash'),
    'cashbook_entries': (),
    'issued_invoices': ('idempotency',),
    'bank_imports': (),
    'bank_transactions': ('dedupe_key',),
    'staff_members': (),
    'shifts': ('idempotency_key', 'request_hash'),
    'cash_closes': (),
    'audit_events': (),
}


def _safe(name: str, fallback: str) -> str:
    plain = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode()
    plain = re.sub(r'[^A-Za-z0-9._-]+', '_', plain).strip('._')[:80]
    return plain or fallback


def _rows(db, table: str, org_id: str) -> list[dict]:
    if table == 'organizations':
        query, args = 'SELECT * FROM organizations WHERE id=?', (org_id,)
    elif table == 'memberships':
        query = ('SELECT m.user_id, u.display_name, m.role FROM memberships m '
                 'JOIN users u ON u.id=m.user_id WHERE m.organization_id=? ORDER BY m.role, u.display_name')
        args = (org_id,)
    elif table == 'task_comments':
        query = "SELECT * FROM task_comments WHERE organization_id=? AND visibility='client' ORDER BY created_at"
        args = (org_id,)
    else:
        query, args = f'SELECT * FROM {table} WHERE organization_id=?', (org_id,)  # table names are constants
    hidden = set(TABLES[table])
    return [{k: v for k, v in dict(row).items() if k not in hidden} for row in db.execute(query, args).fetchall()]


def build_export(org_id: str) -> tuple[tempfile.SpooledTemporaryFile, dict]:
    made = datetime.now(timezone.utc).isoformat(timespec='seconds')
    spool = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)
    counts, unreadable = {}, []
    with zipfile.ZipFile(spool, 'w', zipfile.ZIP_DEFLATED) as archive, connection() as db:
        for table in TABLES:
            rows = _rows(db, table, org_id)
            counts[table] = len(rows)
            archive.writestr(f'data/{table}.json', json.dumps(rows, ensure_ascii=False, indent=1, default=str))
        for doc in db.execute('SELECT id, filename, storage_path FROM documents WHERE organization_id=? ORDER BY created_at',
                              (org_id,)).fetchall():
            path = Path(doc['storage_path'])
            try:
                content = unseal(path.read_bytes(), document_context(org_id, doc['id']))
            except (OSError, InvalidTag):
                unreadable.append(f"document {doc['id']} ({doc['filename']})")
                continue
            archive.writestr(f"originals/documents/{doc['id']}-{_safe(doc['filename'], 'document')}", content)
        for st in db.execute('SELECT f.import_id, f.content, i.filename FROM bank_import_files f JOIN bank_imports i '
                             'ON i.id=f.import_id WHERE f.organization_id=? ORDER BY i.imported_at', (org_id,)).fetchall():
            try:
                content = unseal(st['content'], statement_context(org_id, st['import_id']))
            except InvalidTag:
                unreadable.append(f"statement {st['import_id']} ({st['filename']})")
                continue
            archive.writestr(f"originals/statements/{st['import_id']}-{_safe(st['filename'], 'statement')}", content)
        readme = io.StringIO()
        readme.write(f'VietBiz export\nCompany: {org_id}\nCreated (UTC): {made}\n\n')
        readme.write('data/<table>.json  rows of this company per table (UTF-8 JSON; money as decimal strings)\n')
        readme.write('originals/         uploaded documents and bank statement files, decrypted\n\n')
        readme.write('Rows per table:\n' + ''.join(f'  {t}: {n}\n' for t, n in counts.items()))
        readme.write('\nNot included: accountant-only task notes, internal request keys, server file paths.\n')
        if unreadable:
            readme.write('\nCould not be opened (ask the operator):\n' + ''.join(f'  {u}\n' for u in unreadable))
        archive.writestr('README.txt', readme.getvalue())
    spool.seek(0)
    return spool, {'tables': counts, 'unreadable': len(unreadable), 'created_at': made}


def build_router(current_user, authorize, audit):
    router = APIRouter(prefix='/v1/organizations/{org_id}')

    @router.get('/export')
    def export(org_id: str, uid: str = Depends(current_user)):
        """The company's data and originals as one ZIP (owner only)."""
        with connection() as db:
            authorize(db, uid, org_id, ('owner',))
            audit(db, org_id, uid, 'organization.exported', None)
        spool, _ = build_export(org_id)
        name = f"vietbiz-export-{org_id[:8]}-{datetime.now(timezone.utc).date().isoformat()}.zip"

        def chunks():
            try:
                while block := spool.read(1024 * 1024):
                    yield block
            finally:
                spool.close()

        return StreamingResponse(chunks(), media_type='application/zip',
                                 headers={'Content-Disposition': attachment_disposition(name, 'export.zip')})

    return router
