"""Read VAT data from an ISDOC 6.0.x invoice embedded in an uploaded PDF (ISDOC.PDF).

ISDOC is the Czech national e-invoice standard (Ministry of the Interior; 6.0.2 of
2022-03-23 adds ISDOC.PDF: the XML embedded in a PDF/A-3). Reading it gives exact figures
without OCR. Element names follow isdoc-invoice-6.0.2.xsd (namespace
http://isdoc.cz/namespace/2013).

Safety: the PDF and XML are untrusted. Any problem means "no import" and the upload
continues unchanged. DTDs and entities are refused; sizes are capped; amounts must be
exact at two decimals, so nothing is rounded silently. Only tax documents are imported:
DocumentType 1 (invoice) and 7 (simplified tax document) with VATApplicable=true.
"""
from __future__ import annotations

import io
import logging
import xml.etree.ElementTree as ET
import zlib
from datetime import date
from decimal import Decimal, InvalidOperation

NS = 'http://isdoc.cz/namespace/2013'
MAX_XML_BYTES = 2 * 1024 * 1024
MAX_ATTACHMENTS = 10
SUPPORTED_TYPES = {'1', '7'}  # invoice, simplified tax document
TWO_PLACES = Decimal('0.01')
MAX_AMOUNT = Decimal('1e12')  # matches the 12 integer digits accepted by the API
log = logging.getLogger(__name__)


class NotImportable(ValueError):
    """The XML is not an ISDOC tax document this module can import exactly."""


def _q(path: str) -> str:
    return '/'.join(f'{{{NS}}}{part}' for part in path.split('/'))


def _text(node, path):
    found = node.find(_q(path)) if node is not None else None
    if found is None or found.text is None or not found.text.strip():
        return None
    return found.text.strip()


def _bool(value):
    if value is None:
        return None
    lowered = value.lower()
    if lowered in ('true', '1'):
        return True
    if lowered in ('false', '0'):
        return False
    raise NotImportable('invalid boolean')


def _amount(value):
    if value is None:
        return None
    try:
        number = Decimal(value)
        if not number.is_finite() or abs(number) >= MAX_AMOUNT:
            raise NotImportable('amount out of range')
        exact = number.quantize(TWO_PLACES)
    except InvalidOperation:
        raise NotImportable('invalid amount') from None
    if number != exact:
        raise NotImportable('amount not exact at two decimals')
    return str(exact)


def _rate(value):
    if value is None:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise NotImportable('invalid rate') from None
    if not number.is_finite() or number < 0 or number >= 100 or number != number.quantize(TWO_PLACES):
        raise NotImportable('invalid rate')
    normal = number.normalize()
    return format(normal, 'f')


def _date(value):
    if value is None:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise NotImportable('invalid date') from None


def _party(party):
    if party is None:
        return None, None
    name = _text(party, 'PartyName/Name')
    address = party.find(_q('PostalAddress'))
    street = ' '.join(p for p in (_text(address, 'StreetName'), _text(address, 'BuildingNumber')) if p)
    city = ' '.join(p for p in (_text(address, 'PostalZone'), _text(address, 'CityName')) if p)
    seat = ', '.join(p for p in (street, city) if p)
    label = ', '.join(p for p in (name, seat) if p) or None
    vat_id = None
    for scheme in party.findall(_q('PartyTaxScheme')):
        if (_text(scheme, 'TaxScheme') or '').upper() == 'VAT':
            vat_id = _text(scheme, 'CompanyID')
            break
    return (label[:200] if label else None), (vat_id[:20] if vat_id else None)


def parse_invoice(xml: bytes) -> dict:
    """Map one ISDOC invoice to the CR-1 `fields` shape. Raises NotImportable."""
    if len(xml) > MAX_XML_BYTES:
        raise NotImportable('xml too large')
    # Security review 11.11.2026: look for a DTD in the whole document, not only its first 4 KB
    # (a long comment before the root used to push a DOCTYPE past the check).
    upper = xml.upper()
    if b'<!DOCTYPE' in upper or b'<!ENTITY' in upper:
        raise NotImportable('dtd or entities are not allowed')
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise NotImportable('not well-formed xml') from None
    if root.tag != f'{{{NS}}}Invoice':
        raise NotImportable('not an ISDOC 2013 invoice')
    if not (root.get('version') or '').startswith('6.'):
        raise NotImportable('unsupported ISDOC version')
    if _text(root, 'DocumentType') not in SUPPORTED_TYPES:
        raise NotImportable('not an invoice or simplified tax document')
    if _bool(_text(root, 'VATApplicable')) is not True:
        raise NotImportable('document is not subject to VAT')

    issue_date = _date(_text(root, 'IssueDate'))
    tax_point = _date(_text(root, 'TaxPointDate'))
    supplier_name, supplier_vat_id = _party(root.find(_q('AccountingSupplierParty/Party')))
    customer_name, customer_vat_id = _party(root.find(_q('AccountingCustomerParty/Party')))

    descriptions = [_text(line, 'Item/Description') for line in root.findall(_q('InvoiceLines/InvoiceLine'))]
    subject = '; '.join(d for d in descriptions if d)[:500] or None

    lines, reverse_charge, exempt = [], False, False
    for sub in root.findall(_q('TaxTotal/TaxSubTotal')):
        category = sub.find(_q('TaxCategory'))
        if _bool(_text(category, 'LocalReverseChargeFlag')):
            reverse_charge = True
        vat_applies = _bool(_text(category, 'VATApplicable'))
        rate = _rate(_text(category, 'Percent'))
        if vat_applies is False:
            exempt = True
            rate = None
        lines.append({'rate': rate, 'base': _amount(_text(sub, 'TaxableAmount')),
                      'tax': None if rate is None else _amount(_text(sub, 'TaxAmount'))})
    if not lines or len(lines) > 10:
        raise NotImportable('unexpected number of tax subtotals')
    for line in root.findall(_q('InvoiceLines/InvoiceLine')):
        if line.find(_q('ClassifiedTaxCategory/LocalReverseCharge')) is not None:
            reverse_charge = True

    return {
        'supplier_name': supplier_name, 'supplier_vat_id': supplier_vat_id,
        'document_number': (_text(root, 'ID') or '')[:64] or None, 'subject': subject,
        'issue_date': issue_date, 'supply_date': tax_point if tax_point != issue_date else None,
        'customer_name': customer_name, 'customer_vat_id': customer_vat_id,
        'currency': (_text(root, 'LocalCurrencyCode') or 'CZK').upper(),
        'total': _amount(_text(root, 'LegalMonetaryTotal/TaxInclusiveAmount')),
        'exempt': exempt, 'reverse_charge': reverse_charge, 'lines': lines,
    }


def goods_lines(xml: bytes) -> list[dict]:
    """The invoice's goods lines in the CR-9 shape; [] when absent or not usable.

    Called only on XML that `parse_invoice` accepted. Lines are best effort: one unusable line
    drops them all, so the document never carries a partial list that looks complete.
    """
    root = ET.fromstring(xml)
    out = []
    found = root.findall(_q('InvoiceLines/InvoiceLine'))
    if len(found) > 500:  # Codex review, PR #14: too many to store means none, not the first 500
        return []
    for line in found:
        quantity = line.find(_q('InvoicedQuantity'))
        try:
            qty = Decimal((quantity.text or '').strip()) if quantity is not None else None
            price = Decimal(_text(line, 'UnitPrice') or 'NaN')
        except InvalidOperation:
            return []
        net = _amount(_text(line, 'LineExtensionAmount'))
        name = _text(line, 'Item/Description')
        rate = _rate(_text(line, 'ClassifiedTaxCategory/Percent'))
        if qty is None or not qty.is_finite() or qty == 0 or not price.is_finite() or price < 0 or not name or net is None:
            return []
        out.append({'item_code': (_text(line, 'Item/SellersItemIdentification/ID') or '')[:40] or None,
                    'name': name[:200], 'quantity': str(qty), 'unit': (quantity.get('unitCode') or 'ks')[:10],
                    'unit_price': str(price), 'vat_rate': rate if rate in ('0', '10', '12', '15', '21') else None,
                    'net': net})
    return out


def _attachment_bytes(embedded) -> bytes | None:
    """Return at most MAX_XML_BYTES of one attachment without letting pypdf inflate it.

    Only unfiltered or plain FlateDecode streams are read; inflation stops at the limit.
    """
    files = embedded.pdf_object.get('/EF')
    target = files.get('/UF') or files.get('/F') if files is not None else None
    stream = target.get_object() if target is not None else None
    raw = getattr(stream, '_data', None)
    if not isinstance(raw, bytes) or len(raw) > MAX_XML_BYTES:
        return None
    filters = stream.get('/Filter')
    if stream.get('/DecodeParms') is not None:
        return None
    if filters is None:
        return raw
    if filters in ('/FlateDecode', ['/FlateDecode']):
        inflater = zlib.decompressobj()
        data = inflater.decompress(raw, MAX_XML_BYTES + 1)
        if len(data) > MAX_XML_BYTES or inflater.unconsumed_tail:
            return None
        return data
    return None


def from_pdf(content: bytes) -> dict | None:
    """Return CR-1 fields from the first importable ISDOC attachment, or None.

    Attachment metadata is walked lazily: at most MAX_ATTACHMENTS are looked at, and
    each is read through `_attachment_bytes`, so a small upload cannot inflate into a
    large amount of memory. Every PDF error means "no import".
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted:
            return None
        for index, embedded in enumerate(reader.attachment_list):
            if index >= MAX_ATTACHMENTS:
                break
            payload = _attachment_bytes(embedded)
            if not payload or b'isdoc.cz/namespace/2013' not in payload:
                continue
            try:
                fields = parse_invoice(payload)
                try:
                    fields['goods_lines'] = goods_lines(payload)
                except Exception:  # goods lines are optional; the invoice data still imports
                    fields['goods_lines'] = []
                return fields
            except NotImportable as reason:
                log.info('ISDOC attachment %r not imported: %s', str(embedded.name)[:80], reason)
    except Exception:  # untrusted PDF: never let parsing break the upload
        log.info('ISDOC: PDF attachments not readable')
    return None
