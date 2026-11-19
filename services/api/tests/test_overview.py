"""Owner money overview: money in/out by month, VAT by rate, unpaid supplier invoices.
Synthetic data only."""
from uuid import uuid4

import test_pohoda_export as px
from test_api import c, h
from test_archive import company
from test_cashbook import entry


def overview(org, who, **params):
    return c.get(f'/v1/organizations/{org}/reports/overview', headers=h(who), params={'to': '2026-10', **params})


def month(body, m='2026-10'):
    return next(x for x in body['months'] if x['month'] == m)


def test_money_in_and_out_by_month_method_and_group():
    owner, accountant, _, org = company()
    assert entry(org, owner, kind='income', category='sales', method='cash', amount='1120', vat_rate='12').status_code == 201
    assert entry(org, owner, kind='income', category='sales', method='card', amount='605', vat_rate='21').status_code == 201
    assert entry(org, owner, kind='income', category='sales', method='bank', amount='300').status_code == 201
    assert entry(org, owner, category='goods', amount='500').status_code == 201
    assert entry(org, owner, category='supplies', amount='100').status_code == 201
    assert entry(org, owner, category='rent', amount='2000').status_code == 201
    assert entry(org, owner, category='wages', amount='3000').status_code == 201
    assert entry(org, owner, category='utilities', amount='50').status_code == 201
    assert entry(org, owner, category='goods', currency='EUR', amount='40').status_code == 201
    assert entry(org, owner, entry_date='2026-09-30', category='goods', amount='999').status_code == 201
    r = overview(org, accountant, months=2)
    assert r.status_code == 200
    body = r.json()
    assert [m['month'] for m in body['months']] == ['2026-09', '2026-10']
    oct_ = month(body)
    assert oct_['income'] == {'cash': '1120.00', 'card': '605.00', 'bank': '300.00', 'total': '2025.00'}
    assert oct_['expense'] == {'goods': '600.00', 'wages': '3000.00', 'rent': '2000.00', 'other': '50.00', 'total': '5650.00'}
    assert oct_['net'] == '-3625.00' and month(body, '2026-09')['expense']['goods'] == '999.00'
    assert body['skipped']['currency'] == 1
    # Not a VAT payer: counter sales keep their gross as base, no VAT is due.
    assert body['vat_payer'] is False and oct_['vat_due'] is None
    assert oct_['sales']['12'] == {'base': '1120.00', 'tax': '0.00', 'gross': '1120.00'}
    assert oct_['sales_unknown'] == '300.00'


def test_vat_payer_gets_output_and_input_vat_by_rate():
    owner, accountant, _, org, did = px.company_with_month()
    assert entry(org, owner, kind='income', category='sales', method='cash', amount='1120', vat_rate='12').status_code == 201
    assert entry(org, owner, kind='income', category='sales', method='card', amount='605', vat_rate='21').status_code == 201
    body = overview(org, owner, months=1).json()
    oct_ = month(body)
    assert body['vat_payer'] is True
    # Counter sales: 1120 incl. 12 % → 120 VAT; 605 incl. 21 % → 105 VAT. Issued invoice adds its rates.
    assert oct_['sales']['12'] == {'base': '1091.00', 'tax': '130.92', 'gross': '1221.92'}
    assert oct_['sales']['21'] == {'base': '799.70', 'tax': '167.94', 'gross': '967.64'}
    assert oct_['purchases']['12'] == {'base': '2000.00', 'tax': '240.00', 'gross': '2240.00'}
    assert oct_['purchases']['21'] == {'base': '800.00', 'tax': '168.00', 'gross': '968.00'}
    assert (oct_['vat_out'], oct_['vat_in'], oct_['vat_due']) == ('298.86', '408.00', '-109.14')
    # The approved received invoice has no payment yet.
    assert [u['document_id'] for u in body['unpaid']] == [did]
    assert body['unpaid'][0]['total'] == '3208.00'
    pay = entry(org, owner, category='goods', amount='3208', document_id=did)
    assert pay.status_code == 201
    assert overview(org, owner, months=1).json()['unpaid'] == []


def test_vat_rate_only_on_income_and_old_retries_still_match():
    owner, _, _, org = company()
    assert entry(org, owner, vat_rate='21').status_code == 422  # an expense
    assert entry(org, owner, kind='income', category='sales', vat_rate='15').status_code == 422
    key = str(uuid4())
    first = entry(org, owner, key=key, kind='income', category='sales')
    again = entry(org, owner, key=key, kind='income', category='sales')
    assert (first.status_code, again.status_code) == (201, 200) and first.json()['vat_rate'] is None


def test_only_owner_and_accountant_of_the_company():
    owner, accountant, employee, org = company()
    stranger, *_ = company()
    assert overview(org, employee).status_code == 403
    assert overview(org, stranger).status_code == 403
    assert overview(org, owner, to='2026-13').status_code == 422
    assert overview(org, owner, months=25).status_code == 422
    assert len(overview(org, owner).json()['months']) == 12
