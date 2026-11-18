"""Hand a month's invoices to the accountant's POHODA (Stormware) as an XML data pack.

`GET /v1/organizations/{org}/exports/pohoda?month=YYYY-MM` — owner or accountant — answers one
`dat:dataPack` (version 2.0) with:

- every **issued** invoice of the month (`inv:invoiceType` issuedInvoice; our number as
  `numberRequested` with duplicity check, so importing twice does not create two invoices);
- every **approved received** invoice of the month (receivedInvoice; the supplier's number as
  `originalDocument`), from the latest confirmed extraction.

Amounts go into `inv:invoiceSummary/inv:homeCurrency` per VAT rate: 21 % → priceHigh, 12 % →
priceLow, 0 % / exempt → priceNone; no line items, no accounting assignment
(`withoutAccounting`), so the accountant pre-codes and posts them in POHODA. Received invoices that
cannot go into the pack (another currency than CZK; VAT lines without amounts that the total
cannot fill in) are left out and named in `X-VietBiz-Skipped` (`id:reason`); a month where every
invoice is left out answers 422 with the list. Element order follows Stormware's XSD (version_2: data, invoice, type), checked
with xmllint; the file is Windows-1250 like Stormware's own samples, characters outside it as
numeric references. Owner decision / report step 2 (17.11.2026): accountants keep POHODA.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from .database import connection
from .web_security import attachment_disposition

DAT = 'http://www.stormware.cz/schema/version_2/data.xsd'
INV = 'http://www.stormware.cz/schema/version_2/invoice.xsd'
TYP = 'http://www.stormware.cz/schema/version_2/type.xsd'
for _prefix, _ns in (('dat', DAT), ('inv', INV), ('typ', TYP)):
    ET.register_namespace(_prefix, _ns)

RATE_SLOT = {Decimal('21'): 'High', Decimal('12'): 'Low'}
ZIP_CITY = re.compile(r'^(?P<street>.+?),\s*(?P<zip>\d{3}\s?\d{2})\s+(?P<city>.+)$')


def _el(parent, ns, tag, text=None, **attrs):
    node = ET.SubElement(parent, f'{{{ns}}}{tag}', attrs)
    if text is not None:
        node.text = str(text)
    return node


def _money(value) -> str:
    return str(Decimal(value).quantize(Decimal('0.01')))


def _cut(value, size):
    return (value or '').strip()[:size] or None


def _address(parent, name, address, ico, dic):
    """typ:address/typ:addressType in schema order: company, city, street, zip, ico, dic."""
    identity = _el(parent, INV, 'partnerIdentity')
    box = _el(identity, TYP, 'address')
    street, zip_code, city = None, None, None
    match = ZIP_CITY.match((address or '').strip())
    if match:
        street, zip_code, city = match['street'], match['zip'], match['city']
    elif address:
        street = address
    for tag, value, size in (('company', name, 255), ('city', city, 45), ('street', street, 64),
                             ('zip', zip_code, 15), ('ico', ico, 15), ('dic', dic, 18)):
        value = _cut(value, size)
        if value:
            _el(box, TYP, tag, value)


def _summary(invoice, rates, payer):
    """Bases and VAT per slot, rates: [(rate or None, base, tax)]; anything without a 21/12 % rate
    (non-payer, exempt, reverse charge, 0 %) goes to priceNone with its tax."""
    home = _el(_el(invoice, INV, 'invoiceSummary'), INV, 'homeCurrency')
    slots: dict[str, list[Decimal]] = {}
    none = Decimal('0')
    for rate, base, tax in rates:
        slot = RATE_SLOT.get(Decimal(rate)) if payer and rate not in (None, '') else None
        if slot is None:
            none += Decimal(base) + Decimal(tax or 0)
        else:
            current = slots.setdefault(slot, [Decimal('0'), Decimal('0')])
            current[0] += Decimal(base)
            current[1] += Decimal(tax or 0)
    if none or not slots:
        _el(home, TYP, 'priceNone', _money(none))
    for slot in ('Low', 'High'):  # schema order: priceLow* before priceHigh*
        if slot in slots:
            base, tax = slots[slot]
            _el(home, TYP, f'price{slot}', _money(base))
            _el(home, TYP, f'price{slot}VAT', _money(tax))
            _el(home, TYP, f'price{slot}Sum', _money(base + tax))


def _symvar(number):
    digits = re.sub(r'\D', '', number or '')[-10:]
    return digits or None


def _header(invoice, kind):
    header = _el(invoice, INV, 'invoiceHeader')
    _el(header, INV, 'invoiceType', kind)
    return header


def _tail(header, payer, text):
    _el(_el(header, INV, 'accounting'), TYP, 'accountingType', 'withoutAccounting')
    _el(_el(header, INV, 'classificationVAT'), TYP, 'classificationVATType', 'inland' if payer else 'nonSubsume')
    _el(header, INV, 'text', _cut(text, 240) or 'VietBiz')


def issued(pack, row):
    content, totals, supplier = json.loads(row['content']), json.loads(row['totals']), json.loads(row['supplier'])
    payer = bool(totals.get('vat_payer'))
    item = _el(pack, DAT, 'dataPackItem', id=f"VB-OUT-{row['number']}"[:64], version='2.0')
    invoice = _el(item, INV, 'invoice', version='2.0')
    header = _header(invoice, 'issuedInvoice')
    number = _el(header, INV, 'number')
    _el(number, TYP, 'numberRequested', row['number'], checkDuplicity='true')
    if _symvar(row['number']):
        _el(header, INV, 'symVar', _symvar(row['number']))
    _el(header, INV, 'date', content['issue_date'])
    if payer:
        _el(header, INV, 'dateTax', content['supply_date'])
    _el(header, INV, 'dateAccounting', content['issue_date'])
    _el(header, INV, 'dateDue', content['due_date'])
    first = content['lines'][0]['description'] if content.get('lines') else ''
    _tail(header, payer, first)
    _address(header, content['customer_name'], content['customer_address'], content.get('customer_ico'),
             content.get('customer_dic'))
    _el(_el(header, INV, 'paymentType'), TYP, 'paymentType',
        {'bank': 'draft', 'cash': 'cash', 'card': 'creditcard'}[content.get('payment_method', 'bank')])
    _el(header, INV, 'note', f"VietBiz {row['id']}")
    _summary(invoice, [(r['rate'], r['base'], r['tax']) for r in totals['rates']], payer)
    return item


def received_amounts(fields, payer):
    """[(rate, base, tax)] for a received invoice, or None when the recorded data cannot give
    them (Codex review, PR #31: missing line amounts are never read as zero).
    - complete lines (a base everywhere, a tax wherever a VAT rate applies): those lines;
    - no lines: the total, without VAT breakdown;
    - one VAT line without amounts and a total (simplified tax document): VAT from the total,
      tax = total × rate / (100 + rate), base = total − tax;
    - anything else: not exportable."""
    lines = fields.get('lines') or []
    total = fields.get('total')

    def taxed(line):
        return line.get('rate') not in (None, '', '0') and payer

    if lines and all(line.get('base') is not None and (line.get('tax') is not None or not taxed(line)) for line in lines):
        return [(line.get('rate'), line['base'], line.get('tax') or '0') for line in lines]
    if not lines and total:
        return [(None, total, '0')]
    if total and len(lines) == 1 and lines[0].get('base') is None and lines[0].get('tax') is None and taxed(lines[0]):
        rate = Decimal(lines[0]['rate'])
        tax = (Decimal(total) * rate / (100 + rate)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return [(lines[0]['rate'], str(Decimal(total) - tax), str(tax))]
    return None


def received(pack, doc, fields, payer, rates):
    item = _el(pack, DAT, 'dataPackItem', id=f"VB-IN-{doc['id']}"[:64], version='2.0')
    invoice = _el(item, INV, 'invoice', version='2.0')
    header = _header(invoice, 'receivedInvoice')
    number = fields.get('document_number')
    if _symvar(number):
        _el(header, INV, 'symVar', _symvar(number))
    if number:
        _el(header, INV, 'originalDocument', _cut(number, 32))
    issue = fields.get('issue_date')
    _el(header, INV, 'date', issue)
    if payer and fields.get('supply_date'):
        _el(header, INV, 'dateTax', fields['supply_date'])
    _el(header, INV, 'dateAccounting', issue)
    _tail(header, payer and not fields.get('exempt'), fields.get('subject') or doc['filename'])
    name, _, address = (fields.get('supplier_name') or '').partition(',')
    dic = fields.get('supplier_vat_id')
    ico = re.sub(r'^CZ', '', dic) if dic and re.fullmatch(r'CZ\d{8}', dic) else None
    _address(header, name, address.strip(), ico, dic)
    _el(header, INV, 'note', f"VietBiz {doc['id']}")
    _summary(invoice, rates, payer and not fields.get('exempt') and not fields.get('reverse_charge'))
    return item


def build_pack(org_id: str, month: str) -> tuple[bytes, dict]:
    with connection() as db:
        org = db.execute('SELECT o.name, COALESCE(b.ico, o.ico) AS ico, COALESCE(b.vat_payer, 0) AS vat_payer '
                         'FROM organizations o LEFT JOIN billing_profiles b ON b.organization_id=o.id WHERE o.id=?',
                         (org_id,)).fetchone()
        issued_rows = db.execute(
            "SELECT id, number, content, totals, supplier FROM issued_invoices WHERE organization_id=? "
            "AND status='issued' ORDER BY series_year, sequence", (org_id,)).fetchall()
        approved = db.execute(
            'SELECT d.id, d.filename, e.fields FROM documents d JOIN document_extractions e ON e.document_id=d.id '
            "WHERE d.organization_id=? AND d.status='approved' AND e.version=("
            'SELECT MAX(version) FROM document_extractions x WHERE x.document_id=d.id) ORDER BY d.created_at',
            (org_id,)).fetchall()
    attrs = {'id': f'VietBiz-{month}', 'application': 'VietBiz', 'version': '2.0',
             'note': f'VietBiz {month}'}
    if org['ico'] and re.fullmatch(r'\d{8}', org['ico']):
        attrs['ico'] = org['ico']
    pack = ET.Element(f'{{{DAT}}}dataPack', attrs)
    counts, skipped = {'issued': 0, 'received': 0}, []
    for row in issued_rows:
        if json.loads(row['content'])['issue_date'][:7] != month:
            continue
        issued(pack, row)
        counts['issued'] += 1
    payer = bool(org['vat_payer'])
    for doc in approved:
        fields = json.loads(doc['fields'])
        if (fields.get('issue_date') or '')[:7] != month:
            continue
        # Codex review, PR #31: an invoice left out is always named, with the reason.
        if (fields.get('currency') or 'CZK') != 'CZK':
            skipped.append({'document_id': doc['id'], 'filename': doc['filename'], 'reason': 'currency'})
            continue
        rates = received_amounts(fields, payer and not fields.get('exempt') and not fields.get('reverse_charge'))
        if rates is None:
            skipped.append({'document_id': doc['id'], 'filename': doc['filename'], 'reason': 'amounts'})
            continue
        received(pack, doc, fields, payer, rates)
        counts['received'] += 1
    body = ET.tostring(pack, encoding='unicode')
    xml = '<?xml version="1.0" encoding="Windows-1250"?>\n' + body
    return xml.encode('windows-1250', 'xmlcharrefreplace'), {**counts, 'skipped': skipped}


def build_router(current_user, authorize, audit):
    router = APIRouter(prefix='/v1/organizations/{org_id}')

    @router.get('/exports/pohoda')
    def pohoda(org_id: str, month: str = Query(pattern=r'^\d{4}-(0[1-9]|1[0-2])$'), uid: str = Depends(current_user)):
        """The month's issued and approved received invoices as a POHODA XML data pack."""
        with connection() as db:
            authorize(db, uid, org_id, ('owner', 'accountant'))
            audit(db, org_id, uid, 'export.pohoda', None)
        body, counts = build_pack(org_id, month)
        if not counts['issued'] and not counts['received']:
            if counts['skipped']:  # everything of the month needs handling by hand
                raise HTTPException(422, {'message': 'No invoice of this month can be exported',
                                          'skipped': counts['skipped']})
            raise HTTPException(404, 'Nothing to export for this month')
        headers = {'Content-Disposition': attachment_disposition(f'vietbiz-pohoda-{month}.xml', 'pohoda.xml'),
                   'X-VietBiz-Issued': str(counts['issued']), 'X-VietBiz-Received': str(counts['received']),
                   'X-VietBiz-Skipped': ','.join(f"{s['document_id']}:{s['reason']}" for s in counts['skipped'])}
        return Response(body, media_type='application/xml; charset=windows-1250', headers=headers)

    return router
