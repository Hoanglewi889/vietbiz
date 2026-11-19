"""Owner money overview (owner request 19.11.2026: the dashboard "Tiền của các tiệm" in the app).

`GET /v1/organizations/{org}/reports/overview?to=YYYY-MM&months=12` — owner and accountant.
One company per call; the web sums several companies of the same owner itself ("Tất cả tiệm").

Per month, from what VietBiz already holds (cash basis, CZK only; EUR entries are counted
in `skipped`):
- money in by method (cashbook income: cash, card, bank) and money out by group
  (goods = goods + supplies, wages, rent, other = everything else);
- VAT on sales: counter sales (cashbook income with a VAT rate, gross) and issued invoices
  (their rates); income without a rate is `unknown` (no VAT read into it);
- VAT on purchases: approved received invoices by issue month, split by rate as the POHODA
  export reads them; one whose amounts cannot be split is `unknown`;
- VAT due = output VAT − deductible input VAT, only for a VAT payer.
Plus approved received invoices without a recorded payment (`unpaid`).

A management overview, not a VAT return: the accountant files the return.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, Query

from .database import connection
from .pohoda_export import received_amounts
from .tasks import today_prague

MONTH = r'^\d{4}-(0[1-9]|1[0-2])$'
GROUPS = {'goods': 'goods', 'supplies': 'goods', 'wages': 'wages', 'rent': 'rent'}
RATES = ('21', '12', '0')
CENT = Decimal('0.01')


def _m(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _months(to: str, count: int) -> list[str]:
    year, month = int(to[:4]), int(to[5:])
    out = []
    for _ in range(count):
        out.append(f'{year:04d}-{month:02d}')
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return out[::-1]


def _bucket(rate) -> str | None:
    """'21', '12' or '0' for a rate written any way ("21.00", "12.0"); None for any other rate.
    Codex review, PR #33: compared as text, "21.00" fell into the 0 % row with its tax."""
    try:
        value = Decimal(str(rate))
    except (ArithmeticError, ValueError):
        return None
    for key in RATES:
        if value == Decimal(key):
            return key
    return None


def _vat_from_gross(gross: Decimal, rate: str) -> Decimal:
    r = Decimal(rate)
    return (gross * r / (100 + r)).quantize(CENT, rounding=ROUND_HALF_UP) if r else Decimal('0')


def _empty_month(month):
    zero = Decimal('0')
    return {'month': month,
            'income': {'cash': zero, 'card': zero, 'bank': zero},
            'expense': {'goods': zero, 'wages': zero, 'rent': zero, 'other': zero},
            'sales': {r: {'base': zero, 'tax': zero} for r in RATES}, 'sales_unknown': zero,
            'purchases': {r: {'base': zero, 'tax': zero} for r in RATES}, 'purchases_unknown': zero}


def overview(db, org_id: str, to: str, count: int) -> dict:
    months = _months(to, count)
    first, last = months[0], months[-1]
    by_month = {m: _empty_month(m) for m in months}
    skipped = {'currency': 0, 'amounts': 0}
    org = db.execute('SELECT o.id, o.name, COALESCE(b.vat_payer, 0) AS vat_payer FROM organizations o '
                     'LEFT JOIN billing_profiles b ON b.organization_id=o.id WHERE o.id=?', (org_id,)).fetchone()
    payer = bool(org['vat_payer'])

    entries = db.execute('SELECT kind, entry_date, amount, currency, method, category, vat_rate, document_id '
                         'FROM cashbook_entries WHERE organization_id=? AND voided_at IS NULL '
                         'AND entry_date >= ? AND entry_date < ?',
                         (org_id, first + '-01', _after(last))).fetchall()
    for e in entries:
        bucket = by_month.get(e['entry_date'][:7])
        if bucket is None:
            continue
        if e['currency'] != 'CZK':
            skipped['currency'] += 1
            continue
        amount = Decimal(e['amount'])
        if e['kind'] == 'income':
            bucket['income'][e['method']] += amount
            if e['vat_rate'] is not None:
                tax = _vat_from_gross(amount, e['vat_rate']) if payer else Decimal('0')
                bucket['sales'][e['vat_rate']]['base'] += amount - tax
                bucket['sales'][e['vat_rate']]['tax'] += tax
            elif e['category'] == 'sales':
                bucket['sales_unknown'] += amount
        else:
            bucket['expense'][GROUPS.get(e['category'], 'other')] += amount

    for row in db.execute("SELECT content, totals FROM issued_invoices WHERE organization_id=? AND status='issued'",
                          (org_id,)).fetchall():
        content, totals = json.loads(row['content']), json.loads(row['totals'])
        bucket = by_month.get((content.get('issue_date') or '')[:7])
        if bucket is None:
            continue
        if totals.get('currency', 'CZK') != 'CZK':
            skipped['currency'] += 1
            continue
        for r in totals['rates']:
            rate = _bucket(r['rate'] or '0')
            if rate is None:
                bucket['sales_unknown'] += Decimal(r['base']) + Decimal(r['tax'])
                continue
            bucket['sales'][rate]['base'] += Decimal(r['base'])
            bucket['sales'][rate]['tax'] += Decimal(r['tax'])

    approved = db.execute(
        'SELECT d.id, d.filename, e.fields FROM documents d JOIN document_extractions e '
        'ON e.document_id=d.id AND e.organization_id=d.organization_id '
        "WHERE d.organization_id=? AND d.status='approved' AND e.version=("
        'SELECT MAX(version) FROM document_extractions x WHERE x.document_id=d.id) ORDER BY d.created_at',
        (org_id,)).fetchall()
    paid = {r['document_id'] for r in db.execute(
        'SELECT DISTINCT document_id FROM cashbook_entries WHERE organization_id=? '
        'AND document_id IS NOT NULL AND voided_at IS NULL', (org_id,)).fetchall()}
    unpaid = []
    for doc in approved:
        fields = json.loads(doc['fields'])
        currency = fields.get('currency') or 'CZK'
        if doc['id'] not in paid and fields.get('total') and currency == 'CZK':
            unpaid.append({'document_id': doc['id'], 'supplier_name': fields.get('supplier_name') or doc['filename'],
                           'issue_date': fields.get('issue_date'), 'due_date': fields.get('due_date'),
                           'total': _m(Decimal(fields['total']))})
        bucket = by_month.get((fields.get('issue_date') or '')[:7])
        if bucket is None:
            continue
        if currency != 'CZK':
            skipped['currency'] += 1
            continue
        deductible = payer and not fields.get('exempt') and not fields.get('reverse_charge')
        rates = received_amounts(fields, True)
        if rates is None or any(_bucket(rate) is None for rate, _, _ in rates):
            skipped['amounts'] += 1
            if fields.get('total'):
                bucket['purchases_unknown'] += Decimal(fields['total'])
            continue
        for rate, base, tax in rates:
            rate = _bucket(rate)
            base, tax = Decimal(base), Decimal(tax or '0')
            if not deductible:  # VAT a company cannot deduct is part of the cost
                base, tax = base + tax, Decimal('0')
            bucket['purchases'][rate]['base'] += base
            bucket['purchases'][rate]['tax'] += tax

    out = []
    for m in months:
        b = by_month[m]
        income = sum(b['income'].values(), Decimal('0'))
        expense = sum(b['expense'].values(), Decimal('0'))
        vat_out = sum((v['tax'] for v in b['sales'].values()), Decimal('0'))
        vat_in = sum((v['tax'] for v in b['purchases'].values()), Decimal('0'))
        out.append({
            'month': m,
            'income': {k: _m(v) for k, v in b['income'].items()} | {'total': _m(income)},
            'expense': {k: _m(v) for k, v in b['expense'].items()} | {'total': _m(expense)},
            'net': _m(income - expense),
            'sales': {r: {'base': _m(v['base']), 'tax': _m(v['tax']), 'gross': _m(v['base'] + v['tax'])}
                      for r, v in b['sales'].items()},
            'sales_unknown': _m(b['sales_unknown']),
            'purchases': {r: {'base': _m(v['base']), 'tax': _m(v['tax']), 'gross': _m(v['base'] + v['tax'])}
                          for r, v in b['purchases'].items()},
            'purchases_unknown': _m(b['purchases_unknown']),
            'vat_out': _m(vat_out), 'vat_in': _m(vat_in), 'vat_due': _m(vat_out - vat_in) if payer else None,
        })
    unpaid.sort(key=lambda u: (u['due_date'] or '9999', u['supplier_name']))
    return {'organization': {'id': org['id'], 'name': org['name']}, 'vat_payer': payer, 'currency': 'CZK',
            'basis': 'cash', 'is_tax_return': False, 'months': out, 'unpaid': unpaid, 'skipped': skipped}


def _after(month: str) -> str:
    year, m = int(month[:4]), int(month[5:])
    year, m = (year, m + 1) if m < 12 else (year + 1, 1)
    return date(year, m, 1).isoformat()


def build_router(current_user, authorize, audit):
    router = APIRouter(prefix='/v1/organizations/{org_id}')

    @router.get('/reports/overview')
    def get_overview(org_id: str, uid: str = Depends(current_user),
                     to: str | None = Query(default=None, pattern=MONTH),
                     months: int = Query(default=12, ge=1, le=24)):
        """Money in and out, VAT by rate and unpaid supplier invoices, month by month."""
        with connection() as db:
            authorize(db, uid, org_id, ('owner', 'accountant'))
            return overview(db, org_id, to or today_prague()[:7], months)

    return router
