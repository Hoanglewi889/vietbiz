"""Cashbook and monthly report (CR-4): money actually received or paid.

Entries are never edited or deleted: a mistake is voided with a reason and entered again,
so the history stays traceable for the accountant. The report is a management overview
(cash basis), not a tax return or a statement of tax due. Archive invoices are counted
only through the entries that record their payment, so nothing is counted twice.
"""
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .archive import CATEGORIES as EXPENSE_DOCUMENT_CATEGORIES
from .database import connection
from .tasks import Key, digest, today_prague

INCOME_CATEGORIES = ('sales', 'services', 'other')
EXPENSE_CATEGORIES = (*EXPENSE_DOCUMENT_CATEGORIES, 'wages', 'taxes')
# § 4 zákona č. 254/2004 Sb.: payments above 270 000 Kč between the same payer and
# recipient on one calendar day must be cashless; all such payments that day count.
CASH_LIMIT_CZK = Decimal('270000')
MONTH = r'^\d{4}-(0[1-9]|1[0-2])$'
Amount = Annotated[str, Field(pattern=r'^\d{1,12}(\.\d{1,2})?$')]


class EntryIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    kind: Literal['income', 'expense']
    entry_date: date
    amount: Amount
    currency: Literal['CZK', 'EUR'] = 'CZK'
    method: Literal['cash', 'card', 'bank']
    category: str
    counterparty: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    document_id: str | None = Field(default=None, max_length=64)

    @field_validator('counterparty', 'description', 'document_id', mode='before')
    @classmethod
    def blank_is_missing(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode='after')
    def consistent(self):
        allowed = INCOME_CATEGORIES if self.kind == 'income' else EXPENSE_CATEGORIES
        if self.category not in allowed:
            raise ValueError(f'category must be one of {", ".join(allowed)} for {self.kind}')
        if Decimal(self.amount) <= 0:
            raise ValueError('amount must be positive')
        # The business day is Prague's, as in the form, not the server's clock.
        if self.entry_date.isoformat() > today_prague():
            raise ValueError('entry_date cannot be in the future; record money when it moves')
        return self


class VoidIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    reason: str = Field(min_length=3, max_length=300)


COLUMNS = ('id,kind,entry_date,amount,currency,method,category,counterparty,description,'
           'document_id,created_by,created_at,voided_at,voided_by,void_reason')


def _money(value):
    return str(Decimal(value).quantize(Decimal('0.01')))


def _entry(row):
    item = dict(row)
    item.pop('request_hash', None)
    item['amount'] = _money(item['amount'])
    item['voided'] = item['voided_at'] is not None
    return item


def _cash_findings(entries):
    """Same day, same direction and counterparty: CZK cash payments summed against § 4."""
    groups = defaultdict(list)
    for e in entries:
        if e['method'] != 'cash' or e['currency'] != 'CZK':
            continue
        who = (e['counterparty'] or '').casefold()
        groups[(e['entry_date'], e['kind'], who or e['id'])].append(e)
    findings = []
    for (day, kind, _), group in sorted(groups.items()):
        total = sum((Decimal(e['amount']) for e in group), Decimal('0'))
        if total > CASH_LIMIT_CZK:
            findings.append({'code': 'cash_limit_exceeded', 'reference': '§ 4 zákona č. 254/2004 Sb.',
                             'date': day, 'kind': kind, 'counterparty': group[0]['counterparty'],
                             'total': _money(total), 'limit': _money(CASH_LIMIT_CZK),
                             'entry_ids': [e['id'] for e in group]})
    return findings


def _totals(entries):
    out = {}
    for e in entries:
        cur = out.setdefault(e['currency'], {
            'income': Decimal('0'), 'expense': Decimal('0'),
            'income_by_category': defaultdict(Decimal), 'expense_by_category': defaultdict(Decimal),
            'by_method': {m: {'income': Decimal('0'), 'expense': Decimal('0')} for m in ('cash', 'card', 'bank')}})
        amount = Decimal(e['amount'])
        cur[e['kind']] += amount
        cur[e['kind'] + '_by_category'][e['category']] += amount
        cur['by_method'][e['method']][e['kind']] += amount
    return {
        currency: {
            'income': _money(c['income']), 'expense': _money(c['expense']),
            'result': _money(c['income'] - c['expense']),
            'income_by_category': {k: _money(v) for k, v in sorted(c['income_by_category'].items())},
            'expense_by_category': {k: _money(v) for k, v in sorted(c['expense_by_category'].items())},
            'by_method': {m: {k: _money(v) for k, v in d.items()} for m, d in c['by_method'].items()},
        }
        for currency, c in sorted(out.items())
    }


def build_router(current_user, authorize, audit):
    router = APIRouter(prefix='/v1/organizations/{org_id}', tags=['Cashbook'])

    def month_entries(db, org_id, month, include_voided=False):
        rows = db.execute(f'SELECT {COLUMNS} FROM cashbook_entries WHERE organization_id=? '
                          'AND entry_date >= ? AND entry_date <= ? ORDER BY entry_date DESC, created_at DESC',
                          (org_id, month + '-01', month + '-31')).fetchall()
        entries = [_entry(r) for r in rows]
        return entries if include_voided else [e for e in entries if not e['voided']]

    @router.post('/cashbook', status_code=201)
    def create_entry(org_id: str, body: EntryIn, response: Response, idempotency_key: Key,
                     uid: str = Depends(current_user)):
        # A retried submission (lost response) returns the first entry instead of a second one.
        entry_id, now, request_hash = str(uuid4()), datetime.now(timezone.utc).isoformat(), digest(body)
        with connection() as db:
            authorize(db, uid, org_id, ('owner', 'accountant'))
            if body.document_id is not None and db.execute(
                    'SELECT 1 FROM documents WHERE id=? AND organization_id=?',
                    (body.document_id, org_id)).fetchone() is None:
                raise HTTPException(422, 'Unknown document for this company')
            inserted = db.execute(
                       f'INSERT INTO cashbook_entries(organization_id,idempotency_key,request_hash,{COLUMNS}) '
                       'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) '
                       'ON CONFLICT(organization_id,created_by,idempotency_key) DO NOTHING',
                       (org_id, idempotency_key, request_hash, entry_id, body.kind, body.entry_date.isoformat(), _money(body.amount), body.currency,
                        body.method, body.category, body.counterparty, body.description, body.document_id,
                        uid, now, None, None, None))
            row = db.execute(f'SELECT request_hash,{COLUMNS} FROM cashbook_entries WHERE organization_id=? '
                             'AND created_by=? AND idempotency_key=?', (org_id, uid, idempotency_key)).fetchone()
            if row['request_hash'] != request_hash:
                raise HTTPException(409, 'Idempotency key already used for another entry')
            if inserted.rowcount == 1:
                audit(db, org_id, uid, 'cashbook.entry_created', body.document_id)
            else:
                response.status_code = 200
            entry_id = row['id']
            same_day = [e for e in month_entries(db, org_id, body.entry_date.isoformat()[:7])
                        if e['entry_date'] == body.entry_date.isoformat()]
        entry = _entry(row)
        entry['findings'] = [f for f in _cash_findings(same_day) if entry_id in f['entry_ids']]
        return entry

    @router.get('/cashbook')
    def list_entries(org_id: str, uid: str = Depends(current_user),
                     month: str = Query(pattern=MONTH),
                     include_voided: bool = False):
        with connection() as db:
            authorize(db, uid, org_id, ('owner', 'accountant'))
            entries = month_entries(db, org_id, month, include_voided)
        active = [e for e in entries if not e['voided']]
        return {'month': month, 'items': entries, 'totals': _totals(active), 'findings': _cash_findings(active),
                'categories': {'income': list(INCOME_CATEGORIES), 'expense': list(EXPENSE_CATEGORIES)}}

    @router.post('/cashbook/{entry_id}/void')
    def void_entry(org_id: str, entry_id: str, body: VoidIn, uid: str = Depends(current_user)):
        with connection() as db:
            authorize(db, uid, org_id, ('owner', 'accountant'))
            changed = db.execute('UPDATE cashbook_entries SET voided_at=?, voided_by=?, void_reason=? '
                                 'WHERE id=? AND organization_id=? AND voided_at IS NULL',
                                 (datetime.now(timezone.utc).isoformat(), uid, body.reason, entry_id, org_id))
            if changed.rowcount != 1:
                exists = db.execute('SELECT 1 FROM cashbook_entries WHERE id=? AND organization_id=?',
                                    (entry_id, org_id)).fetchone()
                raise HTTPException(409 if exists else 404, 'Entry already voided' if exists else 'Entry not found')
            audit(db, org_id, uid, 'cashbook.entry_voided', None)
            row = db.execute(f'SELECT {COLUMNS} FROM cashbook_entries WHERE id=?', (entry_id,)).fetchone()
        return _entry(row)

    @router.get('/reports/monthly')
    def monthly_report(org_id: str, uid: str = Depends(current_user), month: str = Query(pattern=MONTH)):
        with connection() as db:
            authorize(db, uid, org_id, ('owner', 'accountant'))
            entries = month_entries(db, org_id, month)
            paid = {r['document_id'] for r in db.execute(
                'SELECT DISTINCT document_id FROM cashbook_entries WHERE organization_id=? '
                'AND document_id IS NOT NULL AND voided_at IS NULL', (org_id,)).fetchall()}
            approved = db.execute(
                'SELECT d.id, d.filename, e.fields FROM documents d JOIN document_extractions e '
                'ON e.document_id=d.id AND e.organization_id=d.organization_id '
                "WHERE d.organization_id=? AND d.status='approved' AND e.version=("
                'SELECT MAX(version) FROM document_extractions x WHERE x.document_id=d.id)',
                (org_id,)).fetchall()
        unrecorded = []
        for doc in approved:
            fields = json.loads(doc['fields'])
            if doc['id'] in paid or not fields.get('total') or (fields.get('issue_date') or '')[:7] != month:
                continue
            unrecorded.append({'document_id': doc['id'], 'filename': doc['filename'],
                               'supplier_name': fields.get('supplier_name'),
                               'issue_date': fields.get('issue_date'), 'total': _money(fields['total']),
                               'currency': fields.get('currency') or 'CZK'})
        return {'month': month, 'entries': len(entries), 'totals': _totals(entries),
                'findings': _cash_findings(entries), 'unrecorded_invoices': unrecorded,
                'basis': 'cash', 'is_tax_return': False}

    return router
