"""Digital document archive (CR-3): find, filter, categorise and total stored invoices.

Categories are for the business's own overview (what money went where), not a tax
classification; the accountant still books and decides deductibility.
Filtering runs in Python over the company's documents and their latest invoice-data
revision, which is fine at prototype scale (one company, thousands of documents).
"""
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from .database import connection

Category = Literal['goods', 'supplies', 'utilities', 'rent', 'services', 'equipment', 'transport', 'other']
CATEGORIES = Category.__args__
STATUSES = ('needs_review', 'needs_changes', 'approved', 'rejected')


class CategoryIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    category: Category | None


def supplier_key(fields):
    """One supplier = one DIČ; without a DIČ, the name before the first comma."""
    vat = (fields.get('supplier_vat_id') or '').replace(' ', '').upper()
    if vat:
        return 'vat:' + vat
    name = (fields.get('supplier_name') or '').split(',')[0].strip().casefold()
    return 'name:' + name if name else None


def duplicate_key(fields):
    """Key under which two received invoices are probably the same one (CR-3, widened in CR-11).

    Same supplier (DIČ, else name) and the same document number, ignoring spaces, dashes and
    case; without a number, the same supplier, issue date and total.
    """
    supplier = supplier_key(fields)
    if not supplier:
        return None
    number = ''.join(ch for ch in (fields.get('document_number') or '').casefold() if ch.isalnum())
    if number:
        return (supplier, 'number', number)
    if fields.get('issue_date') and fields.get('total'):
        return (supplier, 'day', fields['issue_date'], str(fields['total']))
    return None


def learn_category(db, org_id, uid, doc_id, fields):
    """After a scan, reuse the category this company last gave the same supplier.

    Applies only to an uncategorised document and only from the company's own history;
    nothing is guessed. Audited as document.auto_categorized.
    """
    key = supplier_key(fields)
    if not key:
        return None
    current = db.execute('SELECT category FROM documents WHERE id=? AND organization_id=?',
                         (doc_id, org_id)).fetchone()
    if current is None or current['category'] is not None:
        return None
    # Each other document counts with its CURRENT supplier only (latest revision), ordered by
    # when its category was last chosen, so the company's latest choice wins.
    history = db.execute(
        'SELECT d.category, e.fields, (SELECT MAX(a.created_at) FROM audit_events a '
        "WHERE a.organization_id=d.organization_id AND a.document_id=d.id "
        "AND a.event IN ('document.categorized','document.auto_categorized')) AS chosen_at "
        'FROM documents d JOIN document_extractions e ON e.document_id=d.id AND e.organization_id=d.organization_id '
        'JOIN (SELECT document_id, MAX(version) AS version FROM document_extractions WHERE organization_id=? '
        'GROUP BY document_id) m ON m.document_id=e.document_id AND m.version=e.version '
        'WHERE d.organization_id=? AND d.id<>? AND d.category IS NOT NULL', (org_id, org_id, doc_id)).fetchall()
    history = sorted(history, key=lambda row: row['chosen_at'] or '', reverse=True)
    category = next((row['category'] for row in history if supplier_key(json.loads(row['fields'])) == key), None)
    if category is None:
        return None
    db.execute('UPDATE documents SET category=? WHERE id=? AND organization_id=? AND category IS NULL',
               (category, doc_id, org_id))
    db.execute('INSERT INTO audit_events VALUES(?,?,?,?,?,?)',
               (str(uuid4()), org_id, uid, 'document.auto_categorized', doc_id, datetime.now(timezone.utc).isoformat()))
    return category


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


def _day(item):
    invoice = item['invoice']
    return ((invoice or {}).get('issue_date') or item['created_at'])[:10]


def _month(item):
    return _day(item)[:7]


def _matches(item, q, month, category, status, date_from=None, date_to=None, flagged=None):
    if status and item['status'] != status:
        return False
    if flagged is not None and item['flagged'] != flagged:
        return False
    if date_from and _day(item) < date_from.isoformat():
        return False
    if date_to and _day(item) > date_to.isoformat():
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


class FlagIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    flagged: bool


def build_router(current_user, authorize, audit):
    router = APIRouter(prefix='/v1/organizations/{org_id}', tags=['Document archive'])

    @router.get('/archive')
    def archive(org_id: str, uid: str = Depends(current_user),
                q: str | None = Query(default=None, max_length=100),
                month: str | None = Query(default=None, pattern=r'^\d{4}-(0[1-9]|1[0-2])$'),
                category: str | None = Query(default=None),
                status: str | None = Query(default=None),
                date_from: date | None = Query(default=None),
                date_to: date | None = Query(default=None),
                flagged: bool | None = Query(default=None)):
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, 'date_from is after date_to')
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
            marked = {r['document_id'] for r in db.execute(
                'SELECT document_id FROM document_flags WHERE organization_id=?', (org_id,)).fetchall()}
        invoices = {row['document_id']: _invoice(row) for row in latest}
        items = [{**dict(d), 'invoice': invoices.get(d['id']), 'flagged': d['id'] in marked} for d in docs]
        # The same supplier and number (or supplier, date and total) on several documents:
        # likely the same invoice twice. Rejected documents do not count.
        keys = {row['document_id']: duplicate_key(json.loads(row['fields'])) for row in latest}
        decided = {d['id']: d['status'] for d in docs}
        seen = defaultdict(list)
        for doc_id, key in keys.items():
            if key and decided.get(doc_id) != 'rejected':
                seen[key].append(doc_id)
        for item in items:
            key = keys.get(item['id'])
            item['possible_duplicates'] = [d for d in seen.get(key, []) if d != item['id']] if key else []
        chosen = [i for i in items if _matches(i, q, month, category, status, date_from, date_to, flagged)]
        return {'items': chosen, 'summary': _summary(chosen), 'categories': list(CATEGORIES),
                'flagged_count': len(marked)}

    def _flag_state(db, org_id, doc_id):
        flagged = db.execute('SELECT 1 FROM document_flags WHERE document_id=? AND organization_id=?',
                             (doc_id, org_id)).fetchone() is not None
        count = db.execute('SELECT COUNT(*) AS n FROM document_flags WHERE organization_id=?', (org_id,)).fetchone()['n']
        return {'flagged': flagged, 'flagged_count': count}

    def _document(db, org_id, doc_id):
        if not db.execute('SELECT 1 FROM documents WHERE id=? AND organization_id=?', (doc_id, org_id)).fetchone():
            raise HTTPException(404, 'Document not found')

    @router.get('/documents/{doc_id}/flag')
    def flag_state(org_id: str, doc_id: str, uid: str = Depends(current_user)):
        """Whether this document is marked "to look at again", and how many are marked in the company."""
        with connection() as db:
            authorize(db, uid, org_id, ('owner', 'accountant'))
            _document(db, org_id, doc_id)
            return _flag_state(db, org_id, doc_id)

    @router.put('/documents/{doc_id}/flag')
    def set_flag(org_id: str, doc_id: str, body: FlagIn, uid: str = Depends(current_user)):
        """Set the mark to the state asked for; sending the same state twice changes nothing."""
        with connection() as db:
            authorize(db, uid, org_id, ('owner', 'accountant'))
            _document(db, org_id, doc_id)
            # Serialise flag changes per company, so two clicks at once cannot both insert.
            db.execute('UPDATE organizations SET id=id WHERE id=?', (org_id,))
            now = _flag_state(db, org_id, doc_id)
            if now['flagged'] != body.flagged:
                if body.flagged:
                    db.execute('INSERT INTO document_flags VALUES(?,?,?,?)',
                               (doc_id, org_id, uid, datetime.now(timezone.utc).isoformat()))
                else:
                    db.execute('DELETE FROM document_flags WHERE document_id=? AND organization_id=?', (doc_id, org_id))
                audit(db, org_id, uid, 'document.flagged' if body.flagged else 'document.unflagged', doc_id)
                now = _flag_state(db, org_id, doc_id)
            return now

    @router.get('/suppliers')
    def suppliers(org_id: str, uid: str = Depends(current_user),
                  year: int | None = Query(default=None, ge=2000, le=2100)):
        """Spending per supplier and per category, from the latest invoice data of each document."""
        with connection() as db:
            authorize(db, uid, org_id, ('owner', 'accountant'))
            rows = db.execute(
                'SELECT d.id, d.category, d.created_at, e.fields FROM documents d JOIN document_extractions e '
                'ON e.document_id=d.id AND e.organization_id=d.organization_id '
                'JOIN (SELECT document_id, MAX(version) AS version FROM document_extractions '
                'WHERE organization_id=? GROUP BY document_id) m ON m.document_id=e.document_id AND m.version=e.version '
                'WHERE d.organization_id=?', (org_id, org_id)).fetchall()
        groups, by_category, uncategorised = {}, defaultdict(lambda: defaultdict(Decimal)), 0
        for row in rows:
            fields = json.loads(row['fields'])
            key, total = supplier_key(fields), fields.get('total')
            if not key or not total:
                continue
            day = fields.get('issue_date') or row['created_at'][:10]
            if year and not day.startswith(str(year)):
                continue
            currency = fields.get('currency') or 'CZK'
            amount = Decimal(total)
            tax = sum((Decimal(line['tax']) for line in fields.get('lines', []) if line.get('tax')), Decimal('0'))
            g = groups.setdefault(key, {'key': key, 'name': (fields.get('supplier_name') or '').split(',')[0].strip(),
                                        'vat_id': fields.get('supplier_vat_id'), 'documents': 0, 'last_date': day,
                                        'totals': defaultdict(lambda: {'total': Decimal('0'), 'tax': Decimal('0')}),
                                        'categories': defaultdict(int), 'months': defaultdict(Decimal)})
            g['documents'] += 1
            g['last_date'] = max(g['last_date'], day)
            g['totals'][currency]['total'] += amount
            g['totals'][currency]['tax'] += tax
            if currency == 'CZK':
                g['months'][day[:7]] += amount
            if row['category']:
                g['categories'][row['category']] += 1
            else:
                uncategorised += 1
            by_category[currency][row['category'] or 'none'] += amount
        money = lambda v: str(v.quantize(Decimal('0.01')))  # noqa: E731
        items = []
        for g in groups.values():
            items.append({
                'key': g['key'], 'name': g['name'], 'vat_id': g['vat_id'], 'documents': g['documents'],
                'last_date': g['last_date'],
                'totals': {c: {'total': money(t['total']), 'tax': money(t['tax'])} for c, t in sorted(g['totals'].items())},
                'category': max(g['categories'], key=g['categories'].get) if g['categories'] else None,
                'months': {m: money(v) for m, v in sorted(g['months'].items())},
            })
        items.sort(key=lambda i: (-Decimal(i['totals'].get('CZK', {}).get('total', '0')), i['name'].casefold()))
        return {'items': items, 'uncategorised_documents': uncategorised,
                'by_category': {c: {k: money(v) for k, v in sorted(cats.items(), key=lambda kv: -kv[1])}
                                for c, cats in sorted(by_category.items())},
                'categories': list(CATEGORIES)}

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
