"""POHODA XML export of a month's invoices for the accountant. Synthetic data only.

The XML is checked against Stormware's own XSD when POHODA_XSD_DIR points at an unpacked
https://www.stormware.cz/xml/schema/all_schema_ver2.zip (data.xsd, invoice.xsd, type.xsd, …);
the schemas are not kept in this repository."""
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import test_extractions as ex
import test_invoicing as inv
from test_api import c, h

DAT = '{http://www.stormware.cz/schema/version_2/data.xsd}'
INV = '{http://www.stormware.cz/schema/version_2/invoice.xsd}'
TYP = '{http://www.stormware.cz/schema/version_2/type.xsd}'


def company_with_month():
    """A VAT payer with one issued invoice and one approved received invoice in October 2026."""
    owner, accountant, employee, org, did = ex.company()
    assert inv.profile(org, owner).status_code == 200
    iid = inv.draft(org, owner).json()['id']
    assert inv.issue(org, owner, iid).status_code == 200
    assert ex.put(org, did, accountant, 0).status_code == 200
    assert c.post(f'/v1/organizations/{org}/documents/{did}/review', headers=h(accountant),
                  json={'decision': 'approve'}).status_code == 200
    return owner, accountant, employee, org, did


def export(org, who, month='2026-10'):
    return c.get(f'/v1/organizations/{org}/exports/pohoda?month={month}', headers=h(who))


def test_the_month_goes_out_as_one_pohoda_data_pack():
    owner, accountant, _, org, did = company_with_month()
    r = export(org, accountant)
    assert r.status_code == 200
    assert r.headers['content-type'].startswith('application/xml')
    assert 'vietbiz-pohoda-2026-10.xml' in r.headers['content-disposition']
    assert r.headers['x-vietbiz-issued'] == '1' and r.headers['x-vietbiz-received'] == '1'
    assert r.content.startswith(b'<?xml version="1.0" encoding="Windows-1250"?>')
    pack = ET.fromstring(r.content)
    assert pack.tag == DAT + 'dataPack' and pack.get('version') == '2.0' and pack.get('ico') == '00000019'
    out, came_in = [i.find(INV + 'invoice') for i in pack.findall(DAT + 'dataPackItem')]

    head = out.find(INV + 'invoiceHeader')
    assert head.findtext(INV + 'invoiceType') == 'issuedInvoice'
    number = head.find(f'{INV}number/{TYP}numberRequested')
    assert number.text.startswith('2026') and number.get('checkDuplicity') == 'true'
    assert head.findtext(INV + 'date') == '2026-10-20' and head.findtext(INV + 'dateTax') == '2026-10-15'
    assert head.findtext(INV + 'dateDue') == '2026-11-03'
    partner = head.find(f'{INV}partnerIdentity/{TYP}address')
    assert [partner.findtext(TYP + k) for k in ('company', 'city', 'street', 'zip', 'ico', 'dic')] == [
        'Synthetic Customer a.s.', 'Brno', 'Vzorová 2', '602 00', '00000027', 'CZ00000027']
    home = out.find(f'{INV}invoiceSummary/{INV}homeCurrency')
    # 3 × 99.90 at 21 % and 2 × 45.50 at 12 %, tax per rate from the summed base
    assert [(e.tag.replace(TYP, ''), e.text) for e in home] == [
        ('priceLow', '91.00'), ('priceLowVAT', '10.92'), ('priceLowSum', '101.92'),
        ('priceHigh', '299.70'), ('priceHighVAT', '62.94'), ('priceHighSum', '362.64')]

    head = came_in.find(INV + 'invoiceHeader')
    assert head.findtext(INV + 'invoiceType') == 'receivedInvoice'
    assert head.findtext(INV + 'originalDocument') == 'SYN-204' and head.findtext(INV + 'symVar') == '204'
    assert head.findtext(f'{INV}accounting/{TYP}accountingType') == 'withoutAccounting'
    partner = head.find(f'{INV}partnerIdentity/{TYP}address')
    assert partner.findtext(TYP + 'company') == 'Synthetic Wholesale s.r.o.'
    assert partner.findtext(TYP + 'dic') == 'CZ00000001' and partner.findtext(TYP + 'ico') == '00000001'
    home = came_in.find(f'{INV}invoiceSummary/{INV}homeCurrency')
    assert [(e.tag.replace(TYP, ''), e.text) for e in home] == [
        ('priceLow', '2000.00'), ('priceLowVAT', '240.00'), ('priceLowSum', '2240.00'),
        ('priceHigh', '800.00'), ('priceHighVAT', '168.00'), ('priceHighSum', '968.00')]
    assert f'VietBiz {did}' == head.findtext(INV + 'note')


def test_only_owner_and_accountant_and_every_export_is_audited():
    owner, accountant, employee, org, _ = company_with_month()
    assert export(org, employee).status_code == 403
    assert export(org, owner).status_code == 200
    events = [e['event'] for e in c.get(f'/v1/organizations/{org}/audit', headers=h(owner)).json()]
    assert events.count('export.pohoda') == 1


def test_other_months_drafts_and_unapproved_documents_stay_out():
    owner, accountant, _, org, did = ex.company()
    assert inv.profile(org, owner).status_code == 200
    assert inv.draft(org, owner).status_code == 201  # a draft, never issued
    assert ex.put(org, did, accountant, 0).status_code == 200  # recorded but not approved
    assert export(org, accountant).status_code == 404
    assert export(org, accountant, '2026-13').status_code == 422


def test_non_payer_and_foreign_currency():
    owner, accountant, _, org, did = ex.company()
    assert inv.profile(org, owner, vat_payer=False, dic=None).status_code == 200
    iid = inv.draft(org, owner, lines=[{**inv.LINES[0], 'vat_rate': None}]).json()['id']
    assert inv.issue(org, owner, iid).status_code == 200
    assert ex.put(org, did, accountant, 0, fields={**ex.FIELDS, 'currency': 'EUR'}).status_code == 200
    assert c.post(f'/v1/organizations/{org}/documents/{did}/review', headers=h(accountant),
                  json={'decision': 'approve'}).status_code == 200
    r = export(org, accountant)
    assert r.headers['x-vietbiz-skipped'] == f'{did}:currency' and r.headers['x-vietbiz-received'] == '0'
    item = ET.fromstring(r.content).find(f'{DAT}dataPackItem/{INV}invoice')
    head = item.find(INV + 'invoiceHeader')
    assert head.findtext(f'{INV}classificationVAT/{TYP}classificationVATType') == 'nonSubsume'
    assert head.find(INV + 'dateTax') is None
    home = item.find(f'{INV}invoiceSummary/{INV}homeCurrency')
    assert [(e.tag.replace(TYP, ''), e.text) for e in home] == [('priceNone', '299.70')]


def test_vietnamese_characters_survive_windows_1250():
    owner, accountant, _, org, _ = company_with_month()
    r = export(org, accountant)
    assert '&#7903;' in r.content.decode('windows-1250')  # "ở" in "Phở bò" as a character reference
    item = ET.fromstring(r.content).find(f'{DAT}dataPackItem/{INV}invoice/{INV}invoiceHeader')
    assert item.findtext(INV + 'text') == 'Phở bò'


def approved(fields):
    """A payer company with one approved received invoice carrying these fields."""
    owner, accountant, _, org, did = ex.company()
    assert inv.profile(org, owner).status_code == 200
    assert ex.put(org, did, accountant, 0, fields=fields).status_code == 200
    assert c.post(f'/v1/organizations/{org}/documents/{did}/review', headers=h(accountant),
                  json={'decision': 'approve'}).status_code == 200
    return accountant, org, did


def amounts(r):
    item = ET.fromstring(r.content).find(f'{DAT}dataPackItem/{INV}invoice')
    return [(e.tag.replace(TYP, ''), e.text) for e in item.find(f'{INV}invoiceSummary/{INV}homeCurrency')]


def test_a_simplified_receipt_gets_its_vat_from_the_total():
    # Codex review, PR #31: missing line amounts are never exported as zero.
    accountant, org, _ = approved({**ex.FIELDS, 'total': '121.00', 'lines': [{'rate': '21'}]})
    assert amounts(export(org, accountant)) == [('priceHigh', '100.00'), ('priceHighVAT', '21.00'), ('priceHighSum', '121.00')]


def test_complete_lines_are_enough_without_a_total():
    fields = {k: v for k, v in ex.FIELDS.items() if k != 'total'}
    accountant, org, _ = approved(fields)
    r = export(org, accountant)
    assert r.headers['x-vietbiz-received'] == '1'
    assert ('priceHighSum', '968.00') in amounts(r)


def test_lines_without_amounts_are_named_not_zeroed():
    fields = {**ex.FIELDS, 'lines': [{'rate': '21'}, {'rate': '12', 'base': '100.00', 'tax': '12.00'}]}
    accountant, org, did = approved(fields)
    r = export(org, accountant)
    assert r.status_code == 422
    assert r.json()['detail']['skipped'] == [{'document_id': did, 'filename': 'receipt.pdf', 'reason': 'amounts'}]


@pytest.mark.skipif(not os.getenv('POHODA_XSD_DIR') or not shutil.which('xmllint'),
                    reason='Stormware XSD (POHODA_XSD_DIR) and xmllint needed')
def test_the_pack_validates_against_stormware_xsd(tmp_path):
    owner, accountant, _, org, _ = company_with_month()
    target = tmp_path / 'pack.xml'
    target.write_bytes(export(org, accountant).content)
    schema = Path(os.environ['POHODA_XSD_DIR']) / 'data.xsd'
    result = subprocess.run(['xmllint', '--noout', '--schema', str(schema), str(target)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
