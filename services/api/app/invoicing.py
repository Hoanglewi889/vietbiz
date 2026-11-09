"""Issued invoices for small businesses (CR-5): drafts, gapless numbers, print data, ISDOC.

Legal basis (zákon č. 235/2004 Sb. as in force from 1 January 2024, verify in e-Sbírka):
- § 29 odst. 1: elements of a tax document, checked with `check_tax_document` before issue
- § 28 odst. 4: a payer issues the document within 15 days of the taxable supply (flagged)
- § 37: tax computed from the base per rate; here rounded half-up to haléře per rate
- § 47: rates 21 % and 12 %
A business that is not a VAT payer issues an invoice without VAT and without a DIČ
requirement; it is still an accounting document (zákon č. 563/1991 Sb., § 11).

An issued invoice never changes: number, supplier snapshot, lines and totals are frozen.
Corrections are a later feature (opravný daňový doklad, § 42–45). Only CZK for now, so
tax in CZK needs no ČNB rate. Numbers are gapless per calendar year of the issue date
(YYYY-NNNN); the company row is locked while a number is assigned.
"""
import json
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

import segno
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .bank import overdue, payments_for
from .database import connection
from .tasks import Key, digest, today_prague
from .tax_document_rules import TaxDocument, VatLine, check_tax_document

CENT = Decimal('0.01')
RATES = ('21', '12')
ISSUE_DAYS = 15
ISDOC_NS = 'http://isdoc.cz/namespace/2013'
Money = Annotated[str, Field(pattern=r'^\d{1,10}(\.\d{1,2})?$')]
Quantity = Annotated[str, Field(pattern=r'^\d{1,7}(\.\d{1,3})?$')]
Text = Annotated[str, Field(min_length=1, max_length=200)]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class ProfileIn(Strict):
    legal_name: Text
    address: str = Field(min_length=5, max_length=300)
    ico: str = Field(pattern=r'^\d{8}$')
    dic: str | None = Field(default=None, pattern=r'^CZ\d{8,10}$')
    vat_payer: bool
    iban: str | None = Field(default=None, pattern=r'^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$')
    register_note: str | None = Field(default=None, max_length=200)

    @field_validator('dic', 'iban', mode='before')
    @classmethod
    def compact_code(cls, value):
        """'cz 123 456 78' -> 'CZ12345678'; blank -> missing."""
        return value.replace(' ', '').upper() or None if isinstance(value, str) else value

    @field_validator('register_note', mode='before')
    @classmethod
    def blank_is_missing(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode='after')
    def payer_needs_dic(self):
        if self.vat_payer and not self.dic:
            raise ValueError('a VAT payer must state its DIČ (§ 29 odst. 1 písm. b)')
        return self


class LineIn(Strict):
    description: Text
    quantity: Quantity
    unit: str = Field(default='ks', min_length=1, max_length=10)
    unit_price: Money
    vat_rate: Literal['21', '12'] | None = None

    @model_validator(mode='after')
    def positive(self):
        if Decimal(self.quantity) <= 0:
            raise ValueError('quantity must be positive')
        return self


class InvoiceIn(Strict):
    issue_date: date
    supply_date: date
    due_date: date
    customer_name: Text
    customer_address: str = Field(min_length=5, max_length=300)
    customer_ico: str | None = Field(default=None, pattern=r'^\d{8}$')
    customer_dic: str | None = Field(default=None, pattern=r'^[A-Z]{2}[A-Z0-9]{2,12}$')
    payment_method: Literal['bank', 'cash', 'card'] = 'bank'
    note: str | None = Field(default=None, max_length=500)
    lines: list[LineIn] = Field(min_length=1, max_length=50)

    @field_validator('customer_ico', 'customer_dic', 'note', mode='before')
    @classmethod
    def blank_is_missing(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode='after')
    def dates(self):
        if self.due_date < self.issue_date:
            raise ValueError('due_date cannot be before issue_date')
        return self


class InvoiceUpdate(InvoiceIn):
    version: int = Field(ge=1, strict=True)


def _cents(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def compute(content, vat_payer):
    """Line amounts, base and tax per rate, total. Tax per rate from the summed base."""
    lines, bases = [], {}
    for line in content['lines']:
        net = _cents(Decimal(line['quantity']) * Decimal(line['unit_price']))
        lines.append({**line, 'net': str(net)})
        key = line['vat_rate'] if vat_payer else None
        bases[key] = bases.get(key, Decimal('0')) + net
    rates = []
    for rate, base in sorted(bases.items(), key=lambda item: -Decimal(item[0] or 0)):
        tax = _cents(base * Decimal(rate) / 100) if rate else Decimal('0.00')
        rates.append({'rate': rate, 'base': str(_cents(base)), 'tax': str(tax)})
    base = sum((Decimal(r['base']) for r in rates), Decimal('0'))
    tax = sum((Decimal(r['tax']) for r in rates), Decimal('0'))
    return {'lines': lines, 'rates': rates, 'base': str(_cents(base)), 'tax': str(_cents(tax)),
            'total': str(_cents(base + tax)), 'currency': 'CZK', 'vat_payer': vat_payer}


def _public(row):
    item = {k: row[k] for k in ('id', 'status', 'version', 'number', 'created_at', 'updated_at',
                                'issued_at', 'issued_by')}
    item['content'] = json.loads(row['content'])
    item['totals'] = json.loads(row['totals'])
    item['supplier'] = json.loads(row['supplier']) if row['supplier'] else None
    item['variable_symbol'] = f"{row['series_year']}{row['sequence']:04d}" if row['number'] else None
    return item


def _profile(db, org_id):
    row = db.execute('SELECT legal_name,address,ico,dic,vat_payer,iban,register_note,updated_at '
                     'FROM billing_profiles WHERE organization_id=?', (org_id,)).fetchone()
    if row is None:
        return None
    profile = dict(row)
    profile['vat_payer'] = bool(profile['vat_payer'])
    return profile


def _tax_document(invoice, supplier, number):
    content, totals = invoice['content'], invoice['totals']
    return TaxDocument(
        supplier_name=f"{supplier['legal_name']}, {supplier['address']}",
        supplier_vat_id=supplier['dic'], document_number=number,
        subject='; '.join(line['description'] for line in content['lines'])[:500],
        issue_date=date.fromisoformat(content['issue_date']),
        supply_date=date.fromisoformat(content['supply_date']),
        customer_name=f"{content['customer_name']}, {content['customer_address']}",
        customer_vat_id=content['customer_dic'],
        lines=tuple(VatLine(rate=Decimal(r['rate']), base=Decimal(r['base']), tax=Decimal(r['tax']))
                    for r in totals['rates']),
        total=Decimal(totals['total']), currency='CZK')


def _findings(result):
    return [{'code': f.code, 'severity': f.severity, 'field': f.field, 'basis': f.basis,
             'detail': {k: str(v) for k, v in f.detail.items()}} for f in result.findings]


def line_taxes(totals):
    """Tax per line that sums exactly to the tax per rate (§ 37 rounds per rate, not per line).

    Each line is rounded on its own; the rate's rounding residual is then spread one haléř at
    a time over its lines, largest first, never taking a line below zero.
    """
    payer = totals['vat_payer']
    taxes = [(_cents(Decimal(line['net']) * Decimal(line['vat_rate']) / 100)
              if payer and line['vat_rate'] else Decimal('0.00')) for line in totals['lines']]
    for r in totals['rates']:
        members = sorted((i for i, line in enumerate(totals['lines']) if payer and line['vat_rate'] == r['rate']),
                         key=lambda i: -Decimal(totals['lines'][i]['net']))
        residual = Decimal(r['tax']) - sum((taxes[i] for i in members), Decimal('0'))
        step = CENT if residual > 0 else -CENT
        while residual and members:
            for i in members:
                if residual and taxes[i] + step >= 0:
                    taxes[i] += step
                    residual -= step
    return taxes


def isdoc_xml(invoice):
    """ISDOC 6.0.2 invoice (DocumentType 1) for an issued invoice, elements in schema order."""
    ET.register_namespace('', ISDOC_NS)
    content, totals, supplier = invoice['content'], invoice['totals'], invoice['supplier']
    payer = totals['vat_payer']

    def el(parent, tag, text=None, **attrs):
        node = ET.SubElement(parent, f'{{{ISDOC_NS}}}{tag}', attrs)
        if text is not None:
            node.text = str(text)
        return node

    def party(parent, name, address, ico, dic):
        p = el(parent, 'Party')
        el(el(p, 'PartyIdentification'), 'ID', ico or '')
        el(el(p, 'PartyName'), 'Name', name)
        postal = el(p, 'PostalAddress')
        el(postal, 'StreetName', address)
        el(postal, 'BuildingNumber', '')
        el(postal, 'CityName', '')
        el(postal, 'PostalZone', '')
        country = el(postal, 'Country')
        el(country, 'IdentificationCode', 'CZ')
        el(country, 'Name', 'Česká republika')
        if dic:
            scheme = el(p, 'PartyTaxScheme')
            el(scheme, 'CompanyID', dic)
            el(scheme, 'TaxScheme', 'VAT')

    root = ET.Element(f'{{{ISDOC_NS}}}Invoice', {'version': '6.0.2'})
    el(root, 'DocumentType', '1')
    el(root, 'ID', invoice['number'])
    el(root, 'UUID', str(uuid5(NAMESPACE_URL, 'vietbiz:invoice:' + invoice['id'])).upper())
    el(root, 'IssueDate', content['issue_date'])
    el(root, 'TaxPointDate', content['supply_date'])
    el(root, 'VATApplicable', 'true' if payer else 'false')
    el(root, 'ElectronicPossibilityAgreementReference', '')
    el(root, 'LocalCurrencyCode', 'CZK')
    el(root, 'CurrRate', '1')
    el(root, 'RefCurrRate', '1')
    party(el(root, 'AccountingSupplierParty'), supplier['legal_name'], supplier['address'],
          supplier['ico'], supplier['dic'] if payer else None)
    party(el(root, 'AccountingCustomerParty'), content['customer_name'], content['customer_address'],
          content['customer_ico'], content['customer_dic'])
    lines = el(root, 'InvoiceLines')
    for index, (line, line_tax) in enumerate(zip(totals['lines'], line_taxes(totals), strict=True), start=1):
        rate = Decimal(line['vat_rate'] or 0) if payer else Decimal(0)
        net = Decimal(line['net'])
        node = el(lines, 'InvoiceLine')
        el(node, 'ID', index)
        el(node, 'InvoicedQuantity', line['quantity'], unitCode=line['unit'])
        el(node, 'LineExtensionAmount', line['net'])
        el(node, 'LineExtensionAmountTaxInclusive', _cents(net + line_tax))
        el(node, 'LineExtensionTaxAmount', line_tax)
        el(node, 'UnitPrice', line['unit_price'])
        el(node, 'UnitPriceTaxInclusive', _cents(Decimal(line['unit_price']) * (1 + rate / 100)))
        category = el(node, 'ClassifiedTaxCategory')
        el(category, 'Percent', format(rate.normalize(), 'f'))
        el(category, 'VATCalculationMethod', '0')
        el(category, 'VATApplicable', 'true' if payer else 'false')
        el(el(node, 'Item'), 'Description', line['description'])
    tax_total = el(root, 'TaxTotal')
    for r in totals['rates']:
        sub = el(tax_total, 'TaxSubTotal')
        el(sub, 'TaxableAmount', r['base'])
        el(sub, 'TaxAmount', r['tax'])
        el(sub, 'TaxInclusiveAmount', _cents(Decimal(r['base']) + Decimal(r['tax'])))
        for tag in ('AlreadyClaimedTaxableAmount', 'AlreadyClaimedTaxAmount', 'AlreadyClaimedTaxInclusiveAmount'):
            el(sub, tag, '0.00')
        el(sub, 'DifferenceTaxableAmount', r['base'])
        el(sub, 'DifferenceTaxAmount', r['tax'])
        el(sub, 'DifferenceTaxInclusiveAmount', _cents(Decimal(r['base']) + Decimal(r['tax'])))
        category = el(sub, 'TaxCategory')
        el(category, 'Percent', r['rate'] or '0')
        el(category, 'VATApplicable', 'true' if payer else 'false')
    el(tax_total, 'TaxAmount', totals['tax'])
    money = el(root, 'LegalMonetaryTotal')
    el(money, 'TaxExclusiveAmount', totals['base'])
    el(money, 'TaxInclusiveAmount', totals['total'])
    for tag in ('AlreadyClaimedTaxExclusiveAmount', 'AlreadyClaimedTaxInclusiveAmount'):
        el(money, tag, '0.00')
    el(money, 'DifferenceTaxExclusiveAmount', totals['base'])
    el(money, 'DifferenceTaxInclusiveAmount', totals['total'])
    el(money, 'PayableRoundingAmount', '0.00')
    el(money, 'PaidDepositsAmount', '0.00')
    el(money, 'PayableAmount', totals['total'])
    if supplier.get('iban') and content['payment_method'] == 'bank':
        means = el(el(root, 'PaymentMeans'), 'Payment')
        el(means, 'PaidAmount', totals['total'])
        el(means, 'PaymentMeansCode', '42')
        details = el(means, 'Details')
        el(details, 'PaymentDueDate', content['due_date'])
        el(details, 'ID', '')
        el(details, 'BankCode', '')
        el(details, 'Name', '')
        el(details, 'IBAN', supplier['iban'])
        el(details, 'BIC', '')
        el(details, 'VariableSymbol', invoice['variable_symbol'])
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='utf-8')


def _spayd_text(value, limit):
    """SPAYD values: no '*' (the field separator), plain ASCII for banks that reject diacritics."""
    plain = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode()
    return ' '.join(plain.replace('*', ' ').split())[:limit]


def spayd(invoice, amount=None):
    """Czech QR payment ("QR Platba", SPAYD 1.0) for an issued invoice paid to the supplier's IBAN.

    Returns None when the invoice cannot be paid by such a code: not issued, not by bank
    transfer, no IBAN on the supplier snapshot, a currency other than CZK or nothing to pay.
    """
    supplier, content, totals = invoice['supplier'], invoice['content'], invoice['totals']
    amount = Decimal(totals['total'] if amount is None else amount)
    if (invoice['status'] != 'issued' or content['payment_method'] != 'bank' or not supplier.get('iban')
            or totals.get('currency', 'CZK') != 'CZK' or not 0 < amount <= Decimal('9999999.99')):
        return None
    iban = supplier['iban'].replace(' ', '').upper()
    return '*'.join([
        'SPD', '1.0', 'ACC:' + iban, 'AM:' + str(amount.quantize(CENT)), 'CC:CZK',
        'DT:' + content['due_date'].replace('-', ''), 'X-VS:' + invoice['variable_symbol'],
        'RN:' + _spayd_text(supplier['legal_name'], 35), 'MSG:' + _spayd_text('Faktura ' + invoice['number'], 60),
    ])


def build_router(current_user, authorize, audit):
    router = APIRouter(prefix='/v1/organizations/{org_id}', tags=['Issued invoices'])
    roles = ('owner', 'accountant')

    def load(db, org_id, invoice_id):
        row = db.execute('SELECT * FROM issued_invoices WHERE id=? AND organization_id=?',
                         (invoice_id, org_id)).fetchone()
        if row is None:
            raise HTTPException(404, 'Invoice not found')
        return row

    @router.get('/billing-profile')
    def get_profile(org_id: str, uid: str = Depends(current_user)):
        with connection() as db:
            authorize(db, uid, org_id, roles)
            return {'profile': _profile(db, org_id)}

    @router.put('/billing-profile')
    def put_profile(org_id: str, body: ProfileIn, uid: str = Depends(current_user)):
        now = datetime.now(timezone.utc).isoformat()
        values = (body.legal_name, body.address, body.ico, body.dic, int(body.vat_payer), body.iban,
                  body.register_note, uid, now)
        with connection() as db:
            authorize(db, uid, org_id, roles)
            db.execute('INSERT INTO billing_profiles(organization_id,legal_name,address,ico,dic,vat_payer,iban,'
                       'register_note,updated_by,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) '
                       'ON CONFLICT(organization_id) DO UPDATE SET legal_name=excluded.legal_name,'
                       'address=excluded.address,ico=excluded.ico,dic=excluded.dic,vat_payer=excluded.vat_payer,'
                       'iban=excluded.iban,register_note=excluded.register_note,updated_by=excluded.updated_by,'
                       'updated_at=excluded.updated_at', (org_id, *values))
            audit(db, org_id, uid, 'billing_profile.updated', None)
            return {'profile': _profile(db, org_id)}

    def check_rates(db, org_id, body):
        profile = _profile(db, org_id)
        payer = bool(profile and profile['vat_payer'])
        for line in body.lines:
            if payer and line.vat_rate is None:
                raise HTTPException(422, 'Each line needs a VAT rate (21 or 12) for a VAT payer')
            if not payer and line.vat_rate is not None:
                raise HTTPException(422, 'A business that is not a VAT payer cannot charge VAT')
        return payer

    @router.post('/invoices', status_code=201)
    def create_invoice(org_id: str, body: InvoiceIn, response: Response, idempotency_key: Key,
                       uid: str = Depends(current_user)):
        now, request_hash = datetime.now(timezone.utc).isoformat(), digest(body)
        content = body.model_dump(mode='json')
        with connection() as db:
            authorize(db, uid, org_id, roles)
            payer = check_rates(db, org_id, body)
            inserted = db.execute(
                'INSERT INTO issued_invoices(id,organization_id,status,version,content,totals,created_by,'
                'created_at,updated_at,idempotency_key,request_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?) '
                'ON CONFLICT(organization_id,created_by,idempotency_key) DO NOTHING',
                (str(uuid4()), org_id, 'draft', 1, json.dumps(content), json.dumps(compute(content, payer)),
                 uid, now, now, idempotency_key, request_hash))
            row = db.execute('SELECT * FROM issued_invoices WHERE organization_id=? AND created_by=? '
                             'AND idempotency_key=?', (org_id, uid, idempotency_key)).fetchone()
            if row['request_hash'] != request_hash:
                raise HTTPException(409, 'Idempotency key already used for another invoice')
            if inserted.rowcount == 1:
                audit(db, org_id, uid, 'invoice.draft_created', None)
            else:
                response.status_code = 200
            return _public(row)

    @router.get('/invoices')
    def list_invoices(org_id: str, uid: str = Depends(current_user),
                      status: Literal['draft', 'issued'] | None = Query(default=None)):
        with connection() as db:
            authorize(db, uid, org_id, roles)
            rows = db.execute('SELECT * FROM issued_invoices WHERE organization_id=? '
                              'ORDER BY status, series_year DESC, sequence DESC, created_at DESC',
                              (org_id,)).fetchall()
            payments = payments_for(db, org_id)
        items = [_public(r) for r in rows if status is None or r['status'] == status]
        for item in items:
            # CR-11: money matched from bank statements; drafts have none.
            item['payment'] = payments.get(item['id'])
        return {'items': items}

    @router.get('/reminders')
    def reminders(org_id: str, uid: str = Depends(current_user)):
        """Overdue invoices per customer, with a QR for what is still owed. Drafts to send by hand."""
        with connection() as db:
            authorize(db, uid, org_id, roles)
            groups = overdue(db, org_id)
            for group in groups:
                for item in group['invoices']:
                    invoice = _public(load(db, org_id, item['id']))
                    payload = spayd(invoice, item['remaining'])
                    item['spayd'] = payload
                    item['qr'] = segno.make(payload, error='m').svg_data_uri(scale=3, border=2) if payload else None
            profile = _profile(db, org_id)
        return {'groups': groups, 'supplier': profile, 'as_of_date': today_prague()}

    @router.get('/invoices/{invoice_id}')
    def get_invoice(org_id: str, invoice_id: str, uid: str = Depends(current_user)):
        with connection() as db:
            authorize(db, uid, org_id, roles)
            return _public(load(db, org_id, invoice_id))

    @router.put('/invoices/{invoice_id}')
    def update_draft(org_id: str, invoice_id: str, body: InvoiceUpdate, uid: str = Depends(current_user)):
        content = body.model_dump(mode='json', exclude={'version'})
        with connection() as db:
            authorize(db, uid, org_id, roles)
            row = load(db, org_id, invoice_id)
            if row['status'] != 'draft':
                raise HTTPException(409, 'An issued invoice cannot be changed')
            payer = check_rates(db, org_id, body)
            changed = db.execute('UPDATE issued_invoices SET content=?, totals=?, version=version+1, updated_at=? '
                                 "WHERE id=? AND organization_id=? AND status='draft' AND version=?",
                                 (json.dumps(content), json.dumps(compute(content, payer)),
                                  datetime.now(timezone.utc).isoformat(), invoice_id, org_id, body.version))
            if changed.rowcount != 1:
                raise HTTPException(409, 'Invoice changed meanwhile; reload it')
            audit(db, org_id, uid, 'invoice.draft_updated', None)
            return _public(load(db, org_id, invoice_id))

    @router.delete('/invoices/{invoice_id}', status_code=204)
    def delete_draft(org_id: str, invoice_id: str, uid: str = Depends(current_user)):
        with connection() as db:
            authorize(db, uid, org_id, roles)
            load(db, org_id, invoice_id)
            gone = db.execute("DELETE FROM issued_invoices WHERE id=? AND organization_id=? AND status='draft'",
                              (invoice_id, org_id))
            if gone.rowcount != 1:
                raise HTTPException(409, 'An issued invoice cannot be deleted')
            audit(db, org_id, uid, 'invoice.draft_deleted', None)
        return Response(status_code=204)

    @router.post('/invoices/{invoice_id}/issue')
    def issue(org_id: str, invoice_id: str, uid: str = Depends(current_user)):
        now = datetime.now(timezone.utc).isoformat()
        with connection() as db:
            authorize(db, uid, org_id, roles)
            # Serialise numbering per company: the next number is taken under this lock.
            db.execute('UPDATE organizations SET id=id WHERE id=?', (org_id,))
            row = load(db, org_id, invoice_id)
            if row['status'] == 'issued':
                return _public(row)
            profile = _profile(db, org_id)
            if profile is None:
                raise HTTPException(422, {'code': 'billing_profile_missing'})
            content = json.loads(row['content'])
            payer = profile['vat_payer']
            if any((line['vat_rate'] is None) == payer for line in content['lines']):
                raise HTTPException(422, {'code': 'vat_status_changed'})
            totals = compute(content, payer)
            year = int(content['issue_date'][:4])
            sequence = db.execute('SELECT COALESCE(MAX(sequence),0)+1 AS n FROM issued_invoices '
                                  'WHERE organization_id=? AND series_year=?', (org_id, year)).fetchone()['n']
            number = f'{year}-{sequence:04d}'
            supplier = {k: profile[k] for k in ('legal_name', 'address', 'ico', 'dic', 'vat_payer', 'iban',
                                                 'register_note')}
            findings = []
            if payer:
                result = check_tax_document(_tax_document({'content': content, 'totals': totals}, supplier, number))
                findings = _findings(result)
                if not result.complete:
                    raise HTTPException(422, {'code': 'tax_document_incomplete', 'findings': findings})
                supply = date.fromisoformat(content['supply_date'])
                if date.fromisoformat(content['issue_date']) > supply + timedelta(days=ISSUE_DAYS):
                    findings.append({'code': 'issued_after_15_days', 'severity': 'review', 'field': 'issue_date',
                                     'basis': '§ 28 odst. 4 zákona č. 235/2004 Sb.', 'detail': {}})
            totals['findings'] = findings
            db.execute("UPDATE issued_invoices SET status='issued', version=version+1, series_year=?, sequence=?, "
                       'number=?, supplier=?, totals=?, issued_by=?, issued_at=?, updated_at=? '
                       "WHERE id=? AND organization_id=? AND status='draft'",
                       (year, sequence, number, json.dumps(supplier), json.dumps(totals), uid, now, now,
                        invoice_id, org_id))
            audit(db, org_id, uid, 'invoice.issued', None)
            return _public(load(db, org_id, invoice_id))

    @router.get('/invoices/{invoice_id}/isdoc')
    def isdoc(org_id: str, invoice_id: str, uid: str = Depends(current_user)):
        with connection() as db:
            authorize(db, uid, org_id, roles)
            invoice = _public(load(db, org_id, invoice_id))
        if invoice['status'] != 'issued':
            raise HTTPException(409, 'Only an issued invoice can be exported')
        return Response(isdoc_xml(invoice), media_type='application/xml', headers={
            'Content-Disposition': f'attachment; filename="faktura-{invoice["number"]}.isdoc"'})

    @router.get('/invoices/{invoice_id}/payment-qr')
    def payment_qr(org_id: str, invoice_id: str, uid: str = Depends(current_user)):
        with connection() as db:
            authorize(db, uid, org_id, roles)
            invoice = _public(load(db, org_id, invoice_id))
        payload = spayd(invoice)
        if payload is None:
            raise HTTPException(409, 'A QR payment needs an issued CZK invoice paid by transfer to the supplier IBAN')
        code = segno.make(payload, error='m', micro=False)
        return {'spayd': payload, 'image': code.svg_data_uri(scale=4, border=2)}

    return router
