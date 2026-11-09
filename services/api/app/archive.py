"""Digital document archive (CR-3): find, filter, categorise and total stored invoices.

Categories are for the business's own overview (what money went where), not a tax
classification; the accountant still books and decides deductibility.
Filtering runs in Python over the company's documents and their latest invoice-data
revision, which is fine at prototype scale (one company, thousands of documents).
"""
import json
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from .database import connection

Category = Literal['goods', 'supplies', 'utilities', 'rent', 'services', 'equipment', 'transport', 'other']
CATEGORIES = Category.__args__
STATUSES = ('needs_review', 'needs_changes', 'approved', 'rejected')


class CategoryIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    category: Category | None


def _invoice(row):
    if row is None:
        return None
    fields = json.loads(row['fields'])
    check = json.loads(row['check_result'])
    taxes = [line.get('tax') for line in fields.get('lines', []) if line.get('tax') is not None]
    return {
        'supplier_name': fields.get('supplier_name'), 'supplier_vat_id': fields.get('supplier_vat_id'),
        'document_number': fields.get('document_number'), 'issue_date': fields.get('issue_date'),
        'currency': fields.get('currency') or 'CZK', 'total': fields.get('total'),
        'tax': str(sum((Decimal(t) for t in taxes), Decimal('0.00'))) if taxes else None,
        'complete': check.get('complete'), 'source': row['source'], 'version': row['version'],
    }


def _month(item):
    invoice = item['invoice']
    when = (invoice or {}).get('issue_date') or item['created_at']
    return when[:7]


def _matches(item, q, month, category, status):
    if status and item['status'] != status:
        return False
    if category == 'none' and item['category'] is not None:
        return False
    if category and category != 'none' and item['category'] != category:
        return False
    if month and _month(item) != month:
        return False
    if q:
        invoice = item['invoice'] or {}
        haystack = ' '.join(str(v) for v in (item['filename'], invoice.get('supplier_name'),
                                             invoice.get('supplier_vat_id'), invoice.get('document_number')) if v)
        if q.casefold() not in haystack.casefold():
            return False
    return True


def _summary(items):
    by_currency = {}
    for item in items:
        invoice = item['invoice']
        if not invoice or invoice['total'] is None:
            continue
        bucket = by_currency.setdefault(invoice['currency'], {'count': 0, 'total': Decimal('0.00'), 'tax': Decimal('0.00')})
        bucket['count'] += 1
        bucket['total'] += Decimal(invoice['total'])
        if invoice['tax'] is not None:
            bucket['tax'] += Decimal(invoice['tax'])
    return {
        'count': len(items),
        'without_data': sum(1 for i in items if not i['invoice']),
        'by_currency': {cur: {'count': b['count'], 'total': str(b['total']), 'tax': str(b['tax'])}
                        for cur, b in sorted(by_currency.items())},
    }


def build_router(current_user, authorize, audit):
    router = APIRouter(prefix='/v1/organizations/{org_id}', tags=['Document archive'])

    @router.get('/archive')
    def archive(org_id: str, uid: str = Depends(current_user),
                q: str | None = Query(default=None, max_length=100),
                month: str | None = Query(default=None, pattern=r'^\d{4}-(0[1-9]|1[0-2])$'),
                category: str | None = Query(default=None),
                status: str | None = Query(default=None)):
        if category is not None and category != 'none' and category not in CATEGORIES:
            raise HTTPException(422, 'Unknown category')
        if status is not None and status not in STATUSES:
            raise HTTPException(422, 'Unknown status')
        with connection() as db:
            authorize(db, uid, org_id, ('owner', 'accountant'))
            docs = db.execute('SELECT id,filename,mime,sha256,size_bytes,status,created_at,category FROM documents '
                              'WHERE organization_id=? ORDER BY created_at DESC', (org_id,)).fetchall()
            latest = db.execute(
                'SELECT e.* FROM document_extractions e JOIN (SELECT document_id, MAX(version) AS version '
                'FROM document_extractions WHERE organization_id=? GROUP BY document_id) m '
                'ON e.document_id=m.document_id AND e.version=m.version WHERE e.organization_id=?',
                (org_id, org_id)).fetchall()
        invoices = {row['document_id']: _invoice(row) for row in latest}
        items = [{**dict(d), 'invoice': invoices.get(d['id'])} for d in docs]
        # Same supplier DIČ + document number on several documents: likely the same invoice twice.
        seen = {}
        for item in items:
            inv = item['invoice']
            if inv and inv['supplier_vat_id'] and inv['document_number']:
                key = (inv['supplier_vat_id'].upper(), inv['document_number'].casefold())
                seen.setdefault(key, []).append(item['id'])
        for item in items:
            inv = item['invoice']
            key = (inv['supplier_vat_id'].upper(), inv['document_number'].casefold()) \
                if inv and inv['supplier_vat_id'] and inv['document_number'] else None
            item['possible_duplicates'] = [d for d in seen.get(key, []) if d != item['id']] if key else []
        chosen = [i for i in items if _matches(i, q, month, category, status)]
        return {'items': chosen, 'summary': _summary(chosen), 'categories': list(CATEGORIES)}

    @router.put('/documents/{doc_id}/category')
    def set_category(org_id: str, doc_id: str, body: CategoryIn, uid: str = Depends(current_user)):
        with connection() as db:
            authorize(db, uid, org_id, ('owner', 'accountant'))
            changed = db.execute('UPDATE documents SET category=? WHERE id=? AND organization_id=?',
                                 (body.category, doc_id, org_id))
            if changed.rowcount != 1:
                raise HTTPException(404, 'Document not found')
            audit(db, org_id, uid, 'document.categorized', doc_id)
        return {'id': doc_id, 'category': body.category}

    return router
