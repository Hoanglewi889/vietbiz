"""ISDOC 6.0.x embedded in an uploaded PDF becomes revision 1 of the invoice data. Synthetic data only."""
import io

import pytest
from pypdf import PdfWriter
from test_api import c, h, user

from app import isdoc, main

NS = 'http://isdoc.cz/namespace/2013'


def invoice_xml(document_type='7', vat_applicable='true', subtotals=None, total='3208.00',
                customer=True, extra_root='', reverse=False):
    subtotals = subtotals or [('12', '2000.00', '240.00'), ('21', '800.00', '168.00')]
    subs = ''.join(
        f'<TaxSubTotal><TaxableAmount>{base}</TaxableAmount><TaxAmount>{tax}</TaxAmount>'
        f'<TaxInclusiveAmount>0</TaxInclusiveAmount><AlreadyClaimedTaxableAmount>0</AlreadyClaimedTaxableAmount>'
        f'<AlreadyClaimedTaxAmount>0</AlreadyClaimedTaxAmount><AlreadyClaimedTaxInclusiveAmount>0</AlreadyClaimedTaxInclusiveAmount>'
        f'<DifferenceTaxableAmount>0</DifferenceTaxableAmount><DifferenceTaxAmount>0</DifferenceTaxAmount>'
        f'<DifferenceTaxInclusiveAmount>0</DifferenceTaxInclusiveAmount>'
        f'<TaxCategory><Percent>{rate}</Percent>'
        f'{"<LocalReverseChargeFlag>true</LocalReverseChargeFlag>" if reverse else ""}</TaxCategory></TaxSubTotal>'
        for rate, base, tax in subtotals)
    party = ('<Party><PartyIdentification><ID>00000002</ID></PartyIdentification>'
             '<PartyName><Name>Synthetic Potraviny s.r.o.</Name></PartyName>'
             '<PostalAddress><StreetName>Ukázková</StreetName><BuildingNumber>2</BuildingNumber>'
             '<CityName>Brno</CityName><PostalZone>60200</PostalZone></PostalAddress>'
             '<PartyTaxScheme><CompanyID>CZ00000002</CompanyID><TaxScheme>VAT</TaxScheme></PartyTaxScheme></Party>')
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="{NS}" version="6.0.2">{extra_root}
  <DocumentType>{document_type}</DocumentType>
  <ID>SYN-ISDOC-7</ID>
  <UUID>00000000-0000-0000-0000-000000000007</UUID>
  <IssueDate>2026-10-30</IssueDate>
  <TaxPointDate>2026-10-29</TaxPointDate>
  <VATApplicable>{vat_applicable}</VATApplicable>
  <ElectronicPossibilityAgreementReference>synthetic</ElectronicPossibilityAgreementReference>
  <LocalCurrencyCode>CZK</LocalCurrencyCode>
  <CurrRate>1</CurrRate><RefCurrRate>1</RefCurrRate>
  <AccountingSupplierParty><Party><PartyIdentification><ID>00000001</ID></PartyIdentification>
    <PartyName><Name>Synthetic Wholesale s.r.o.</Name></PartyName>
    <PostalAddress><StreetName>Testovací</StreetName><BuildingNumber>1</BuildingNumber>
      <CityName>Praha</CityName><PostalZone>11000</PostalZone></PostalAddress>
    <PartyTaxScheme><CompanyID>CZ00000001</CompanyID><TaxScheme>VAT</TaxScheme></PartyTaxScheme>
  </Party></AccountingSupplierParty>
  {f"<AccountingCustomerParty>{party}</AccountingCustomerParty>" if customer else ""}
  <InvoiceLines>
    <InvoiceLine><ID>1</ID><Item><Description>Rýže jasmínová</Description></Item></InvoiceLine>
    <InvoiceLine><ID>2</ID><Item><Description>Čisticí prostředek</Description></Item></InvoiceLine>
  </InvoiceLines>
  <TaxTotal>{subs}<TaxAmount>408.00</TaxAmount></TaxTotal>
  <LegalMonetaryTotal><TaxExclusiveAmount>2800.00</TaxExclusiveAmount>
    <TaxInclusiveAmount>{total}</TaxInclusiveAmount>
    <AlreadyClaimedTaxExclusiveAmount>0</AlreadyClaimedTaxExclusiveAmount>
    <AlreadyClaimedTaxInclusiveAmount>0</AlreadyClaimedTaxInclusiveAmount>
    <DifferenceTaxExclusiveAmount>0</DifferenceTaxExclusiveAmount>
    <DifferenceTaxInclusiveAmount>0</DifferenceTaxInclusiveAmount>
    <PaidDepositsAmount>0</PaidDepositsAmount><PayableAmount>{total}</PayableAmount>
  </LegalMonetaryTotal>
</Invoice>'''.encode()


def pdf_with(attachments):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    for name, data in attachments:
        writer.add_attachment(name, data)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def setup():
    owner, accountant = user('ISDOC owner'), user('ISDOC accountant')
    org = c.post('/v1/organizations', json={'name': 'ISDOC import'}, headers=h(owner)).json()['id']
    invite = c.post(f'/v1/organizations/{org}/members', json={'user_id': accountant, 'role': 'accountant'}, headers=h(owner))
    c.post(f"/v1/invitations/{invite.json()['id']}/accept", headers=h(accountant))
    return owner, accountant, org


def upload(org, who, content):
    r = c.post(f'/v1/organizations/{org}/documents', headers=h(who),
               files={'file': ('invoice.pdf', content, 'application/pdf')})
    assert r.status_code == 201, r.text
    return r.json()['id']


def test_parse_maps_isdoc_to_invoice_fields():
    fields = isdoc.parse_invoice(invoice_xml())
    assert fields['supplier_name'] == 'Synthetic Wholesale s.r.o., Testovací 1, 11000 Praha'
    assert fields['supplier_vat_id'] == 'CZ00000001'
    assert fields['customer_vat_id'] == 'CZ00000002'
    assert fields['document_number'] == 'SYN-ISDOC-7'
    assert fields['issue_date'] == '2026-10-30' and fields['supply_date'] == '2026-10-29'
    assert fields['subject'] == 'Rýže jasmínová; Čisticí prostředek'
    assert fields['total'] == '3208.00' and fields['currency'] == 'CZK'
    assert fields['lines'] == [{'rate': '12', 'base': '2000.00', 'tax': '240.00'},
                               {'rate': '21', 'base': '800.00', 'tax': '168.00'}]
    assert fields['reverse_charge'] is False and fields['exempt'] is False


def test_uploaded_isdoc_pdf_is_read_without_manual_entry():
    owner, accountant, org = setup()
    did = upload(org, owner, pdf_with([('faktura.isdoc', invoice_xml())]))
    data = c.get(f'/v1/organizations/{org}/documents/{did}/extraction', headers=h(accountant))
    assert data.status_code == 200
    body = data.json()
    assert body['version'] == 1 and body['source'] == 'isdoc' and body['updated_by'] == owner
    assert body['check'] == {'kind': 'simplified', 'complete': True, 'findings': []}
    audit = [e['event'] for e in c.get(f'/v1/organizations/{org}/audit', headers=h(owner)).json()
             if e['document_id'] == did]
    assert 'document.extraction_imported' in audit and 'document.uploaded' in audit
    # The accountant's correction becomes a manual revision 2; the import stays as revision 1.
    fixed = c.put(f'/v1/organizations/{org}/documents/{did}/extraction', headers=h(accountant),
                  json={'version': 1, 'fields': {**body['fields'], 'document_number': 'SYN-ISDOC-7A'}})
    assert fixed.status_code == 200 and fixed.json()['source'] == 'manual' and fixed.json()['version'] == 2


def test_imported_data_is_still_checked_against_the_vat_act():
    owner, _, org = setup()
    did = upload(org, owner, pdf_with([('x.isdoc', invoice_xml(total='3308.00'))]))
    check = c.get(f'/v1/organizations/{org}/documents/{did}/extraction', headers=h(owner)).json()['check']
    assert [f['code'] for f in check['findings']] == ['total_mismatch']


@pytest.mark.parametrize('xml, reason', [
    (invoice_xml(document_type='4'), 'not an invoice'),  # proforma, not a tax document
    (invoice_xml(document_type='2'), 'not an invoice'),  # credit note: not modelled yet
    (invoice_xml(vat_applicable='false'), 'not subject to VAT'),
    (invoice_xml(subtotals=[('21', '800.004', '168.00')]), 'two decimals'),
    (invoice_xml(subtotals=[('21', 'abc', '168.00')]), 'invalid amount'),
    (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><Invoice xmlns="' + NS.encode() + b'"/>', 'dtd'),
    (b'<Invoice xmlns="urn:other" version="6.0.2"/>', 'not an ISDOC'),
    (b'<Invoice', 'not well-formed'),
])
def test_unsupported_or_unsafe_xml_is_not_imported(xml, reason):
    with pytest.raises(isdoc.NotImportable, match=reason):
        isdoc.parse_invoice(xml)


def test_reverse_charge_flag_is_carried_over():
    fields = isdoc.parse_invoice(invoice_xml(reverse=True, document_type='1'))
    assert fields['reverse_charge'] is True


@pytest.mark.parametrize('content', [
    pdf_with([]),                                              # ordinary PDF
    pdf_with([('notes.txt', b'hello')]),                        # unrelated attachment
    pdf_with([('bad.isdoc', invoice_xml(document_type='4'))]),  # proforma
    b'%PDF-1.4\n%garbage that is not a real pdf',              # unreadable PDF
])
def test_pdf_without_importable_isdoc_uploads_normally(content):
    owner, _, org = setup()
    did = upload(org, owner, content)
    assert c.get(f'/v1/organizations/{org}/documents/{did}/extraction', headers=h(owner)).status_code == 404
    with main.conn() as db:
        assert db.execute('SELECT COUNT(*) AS n FROM document_extractions WHERE document_id=?',
                          (did,)).fetchone()['n'] == 0


def test_first_importable_attachment_wins():
    fields = isdoc.from_pdf(pdf_with([('a.isdoc', invoice_xml(document_type='4')),
                                      ('b.isdoc', invoice_xml())]))
    assert fields is not None and fields['document_number'] == 'SYN-ISDOC-7'
