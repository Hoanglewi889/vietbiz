"""CR-5 issued invoices: profile, drafts, totals, gapless numbers, immutability, ISDOC. Synthetic data only."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

from app.database import Transaction
from app.isdoc import NotImportable, parse_invoice
from test_api import c, h, user
from test_archive import company

PAYER = {'legal_name': 'Synthetic Bistro s.r.o.', 'address': 'Ukázková 1, 110 00 Praha 1', 'ico': '00000019',
         'dic': 'cz 000 000 19', 'vat_payer': True, 'iban': 'CZ65 0800 0000 1920 0014 5399',
         'register_note': 'Synthetic register entry C 0000'}
LINES = [{'description': 'Phở bò', 'quantity': '3', 'unit': 'ks', 'unit_price': '99.90', 'vat_rate': '21'},
         {'description': 'Catering', 'quantity': '2', 'unit': 'hod', 'unit_price': '45.50', 'vat_rate': '12'}]
INVOICE = {'issue_date': '2026-10-20', 'supply_date': '2026-10-15', 'due_date': '2026-11-03',
           'customer_name': 'Synthetic Customer a.s.', 'customer_address': 'Vzorová 2, 602 00 Brno',
           'customer_ico': '00000027', 'customer_dic': 'CZ00000027', 'lines': LINES}


def url(org, rest=''):
    return f'/v1/organizations/{org}{rest}'


def profile(org, who, **changes):
    return c.put(url(org, '/billing-profile'), headers=h(who), json={**PAYER, **changes})


def draft(org, who, key=None, **changes):
    return c.post(url(org, '/invoices'), json={**INVOICE, **changes},
                  headers={**h(who), 'Idempotency-Key': key or str(uuid4())})


def issue(org, who, iid):
    return c.post(url(org, f'/invoices/{iid}/issue'), headers=h(who))


def payer_company():
    owner, accountant, employee, org = company()
    assert profile(org, owner).status_code == 200
    return owner, accountant, employee, org


def test_profile_normalises_codes_and_requires_dic_for_payers():
    owner, accountant, employee, org = company()
    assert c.get(url(org, '/billing-profile'), headers=h(owner)).json() == {'profile': None}
    saved = profile(org, accountant).json()['profile']
    assert (saved['dic'], saved['iban'], saved['vat_payer']) == ('CZ00000019', 'CZ6508000000192000145399', True)
    assert profile(org, owner, dic='').status_code == 422
    assert profile(org, owner, dic='', vat_payer=False).status_code == 200
    assert profile(org, owner, ico='123').status_code == 422
    assert profile(org, employee).status_code == 403


def test_draft_totals_round_tax_per_rate_half_up():
    owner, _, _, org = payer_company()
    body = draft(org, owner).json()
    assert body['status'] == 'draft' and body['number'] is None
    totals = body['totals']
    assert [line['net'] for line in totals['lines']] == ['299.70', '91.00']
    assert totals['rates'] == [{'rate': '21', 'base': '299.70', 'tax': '62.94'},
                               {'rate': '12', 'base': '91.00', 'tax': '10.92'}]
    assert (totals['base'], totals['tax'], totals['total']) == ('390.70', '73.86', '464.56')


def test_vat_rates_follow_the_payer_status():
    owner, _, _, org = payer_company()
    assert draft(org, owner, lines=[{**LINES[0], 'vat_rate': None}]).status_code == 422
    assert draft(org, owner, lines=[{**LINES[0], 'vat_rate': '15'}]).status_code == 422
    profile(org, owner, dic='', vat_payer=False)
    assert draft(org, owner).status_code == 422
    plain = draft(org, owner, lines=[{**line, 'vat_rate': None} for line in LINES]).json()
    assert plain['totals']['rates'] == [{'rate': None, 'base': '390.70', 'tax': '0.00'}]
    assert plain['totals']['total'] == '390.70'
    issued = issue(org, owner, plain['id']).json()
    assert issued['number'] == '2026-0001' and issued['supplier']['vat_payer'] is False


def test_invalid_drafts_are_rejected():
    owner, _, _, org = payer_company()
    for bad in ({'due_date': '2026-10-01'}, {'lines': []}, {'customer_name': ''},
                {'lines': [{**LINES[0], 'quantity': '0'}]}, {'lines': [{**LINES[0], 'unit_price': '-1'}]},
                {'customer_ico': '12'}, {'extra': True}):
        assert draft(org, owner, **bad).status_code == 422, bad


def test_numbers_are_gapless_per_year_and_issued_invoices_are_frozen():
    owner, accountant, _, org = payer_company()
    first, second, deleted = (draft(org, owner).json()['id'] for _ in range(3))
    next_year = draft(org, owner, issue_date='2027-01-04', supply_date='2027-01-04', due_date='2027-01-18').json()['id']
    assert c.delete(url(org, f'/invoices/{deleted}'), headers=h(owner)).status_code == 204
    assert issue(org, accountant, second).json()['number'] == '2026-0001'
    assert issue(org, owner, first).json()['number'] == '2026-0002'
    assert issue(org, owner, next_year).json()['number'] == '2027-0001'
    again = issue(org, owner, first).json()
    assert again['number'] == '2026-0002' and again['variable_symbol'] == '20260002'
    assert c.put(url(org, f'/invoices/{first}'), headers=h(owner), json={**INVOICE, 'version': again['version']}
                 ).status_code == 409
    assert c.delete(url(org, f'/invoices/{first}'), headers=h(owner)).status_code == 409
    profile(org, owner, legal_name='Renamed Bistro s.r.o.')
    assert c.get(url(org, f'/invoices/{first}'), headers=h(owner)).json()['supplier']['legal_name'] == \
        'Synthetic Bistro s.r.o.'
    events = [e['event'] for e in c.get(url(org, '/audit'), headers=h(owner)).json()]
    assert events.count('invoice.issued') == 3 and 'invoice.draft_deleted' in events


def test_draft_edits_use_versions_and_retries_create_one_draft():
    owner, _, _, org = payer_company()
    key = str(uuid4())
    made = draft(org, owner, key=key)
    assert draft(org, owner, key=key).json()['id'] == made.json()['id']
    assert draft(org, owner, key=key, customer_name='Other').status_code == 409
    iid = made.json()['id']
    edited = c.put(url(org, f'/invoices/{iid}'), headers=h(owner),
                   json={**INVOICE, 'lines': LINES[:1], 'version': 1})
    assert edited.status_code == 200 and edited.json()['totals']['total'] == '362.64'
    assert c.put(url(org, f'/invoices/{iid}'), headers=h(owner), json={**INVOICE, 'version': 1}).status_code == 409
    assert len(c.get(url(org, '/invoices'), headers=h(owner)).json()['items']) == 1


def test_issue_needs_a_profile_and_flags_late_issue():
    owner, _, _, org = company()
    iid = draft(org, owner, lines=[{**line, 'vat_rate': None} for line in LINES]).json()['id']
    assert issue(org, owner, iid).json()['detail'] == {'code': 'billing_profile_missing'}
    profile(org, owner)
    assert issue(org, owner, iid).json()['detail'] == {'code': 'vat_status_changed'}
    late = draft(org, owner, supply_date='2026-09-01').json()['id']
    findings = issue(org, owner, late).json()['totals']['findings']
    assert [f['code'] for f in findings] == ['issued_after_15_days']


def test_concurrent_issues_get_consecutive_numbers(monkeypatch):
    owner, accountant, _, org = payer_company()
    a, b = draft(org, owner).json()['id'], draft(org, owner).json()['id']
    gate, original = Barrier(2), Transaction.execute

    def synchronized(self, statement, parameters=()):
        if statement.startswith('UPDATE organizations SET id=id'):
            gate.wait(timeout=10)
        return original(self, statement, parameters)

    monkeypatch.setattr(Transaction, 'execute', synchronized)
    with ThreadPoolExecutor(max_workers=2) as pool:
        numbers = sorted(pool.map(lambda pair: issue(org, pair[0], pair[1]).json()['number'],
                                  ((owner, a), (accountant, b))))
    monkeypatch.setattr(Transaction, 'execute', original)
    assert numbers == ['2026-0001', '2026-0002']


def test_isdoc_export_round_trips_through_the_importer():
    owner, _, _, org = payer_company()
    iid = draft(org, owner).json()['id']
    assert c.get(url(org, f'/invoices/{iid}/isdoc'), headers=h(owner)).status_code == 409
    issue(org, owner, iid)
    exported = c.get(url(org, f'/invoices/{iid}/isdoc'), headers=h(owner))
    assert exported.status_code == 200 and 'faktura-2026-0001.isdoc' in exported.headers['content-disposition']
    fields = parse_invoice(exported.content)
    assert fields['document_number'] == '2026-0001' and fields['supplier_vat_id'] == 'CZ00000019'
    assert fields['customer_vat_id'] == 'CZ00000027' and fields['total'] == '464.56'
    assert fields['issue_date'] == '2026-10-20' and fields['supply_date'] == '2026-10-15'
    assert fields['lines'] == [{'rate': '21', 'base': '299.70', 'tax': '62.94'},
                               {'rate': '12', 'base': '91.00', 'tax': '10.92'}]
    assert b'<VariableSymbol>20260001</VariableSymbol>' in exported.content


def test_non_payer_isdoc_is_marked_without_vat():
    owner, _, _, org = company()
    profile(org, owner, dic='', vat_payer=False)
    iid = draft(org, owner, lines=[{**line, 'vat_rate': None} for line in LINES]).json()['id']
    issue(org, owner, iid)
    xml = c.get(url(org, f'/invoices/{iid}/isdoc'), headers=h(owner)).content
    assert b'<VATApplicable>false</VATApplicable>' in xml
    with pytest.raises(NotImportable):
        parse_invoice(xml)  # the importer only takes VAT documents, by design


def test_only_finance_roles_of_the_company_see_invoices():
    owner, _, employee, org = payer_company()
    iid = draft(org, owner).json()['id']
    stranger = user('Invoice stranger')
    other_owner, _, _, other_org = company()
    for who in (employee, stranger):
        assert draft(org, who).status_code == 403
        assert c.get(url(org, '/invoices'), headers=h(who)).status_code == 403
        assert issue(org, who, iid).status_code == 403
    for path in (f'/invoices/{iid}', f'/invoices/{iid}/isdoc'):
        assert c.get(url(other_org, path), headers=h(other_owner)).status_code == 404
    assert issue(other_org, other_owner, iid).status_code == 404
