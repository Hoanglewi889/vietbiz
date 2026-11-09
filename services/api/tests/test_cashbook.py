"""CR-4 cashbook and monthly report: totals, void, cash limit, unrecorded invoices, roles. Synthetic data only."""
from uuid import uuid4

import app.cashbook as cashbook
from test_api import c, h, user
from test_archive import company, record, upload

MONTH = '2026-10'


def entry(org, who, key=None, **changes):
    body = {'kind': 'expense', 'entry_date': '2026-10-05', 'amount': '1000', 'currency': 'CZK',
            'method': 'bank', 'category': 'goods', **changes}
    return c.post(f'/v1/organizations/{org}/cashbook', json=body,
                  headers={**h(who), 'Idempotency-Key': key or str(uuid4())})


def book(org, who, **params):
    return c.get(f'/v1/organizations/{org}/cashbook', headers=h(who), params={'month': MONTH, **params})


def report(org, who, month=MONTH):
    return c.get(f'/v1/organizations/{org}/reports/monthly', headers=h(who), params={'month': month})


def test_entries_total_by_currency_category_and_method():
    owner, accountant, _, org = company()
    assert entry(org, owner, kind='income', category='sales', method='cash', amount='12500.5').status_code == 201
    assert entry(org, owner, kind='income', category='sales', method='card', amount='3000').status_code == 201
    assert entry(org, accountant, category='rent', amount='15000').status_code == 201
    assert entry(org, owner, category='goods', method='cash', amount='2499.50').status_code == 201
    assert entry(org, owner, category='goods', currency='EUR', amount='40').status_code == 201
    assert entry(org, owner, entry_date='2026-09-30', amount='999').status_code == 201  # other month
    body = book(org, owner).json()
    assert len(body['items']) == 5 and body['findings'] == []
    czk = body['totals']['CZK']
    assert (czk['income'], czk['expense'], czk['result']) == ('15500.50', '17499.50', '-1999.00')
    assert czk['expense_by_category'] == {'goods': '2499.50', 'rent': '15000.00'}
    assert czk['by_method']['cash'] == {'income': '12500.50', 'expense': '2499.50'}
    assert body['totals']['EUR']['expense'] == '40.00'
    assert 'wages' in body['categories']['expense'] and body['categories']['income'] == ['sales', 'services', 'other']


def test_invalid_entries_are_rejected():
    owner, _, _, org = company()
    for bad in ({'kind': 'income', 'category': 'goods'}, {'category': 'sales'}, {'amount': '0'},
                {'amount': '-5'}, {'amount': '1.234'}, {'method': 'crypto'}, {'currency': 'USD'},
                {'entry_date': '2999-01-01'}, {'unknown': 1}):
        assert entry(org, owner, **bad).status_code == 422, bad
    other_owner, _, _, other_org = company()
    foreign = upload(other_org, other_owner, b'%PDF-1.4\nForeign').json()['id']
    assert entry(org, owner, document_id=foreign).status_code == 422
    assert c.get(f'/v1/organizations/{org}/cashbook', headers=h(owner), params={'month': '2026-13'}).status_code == 422


def test_void_keeps_history_and_leaves_totals():
    owner, accountant, _, org = company()
    wrong = entry(org, owner, amount='5000').json()
    entry(org, owner, amount='500')
    voided = c.post(f"/v1/organizations/{org}/cashbook/{wrong['id']}/void", headers=h(accountant),
                    json={'reason': 'Typo, entered 500 again'})
    assert voided.status_code == 200 and voided.json()['voided'] and voided.json()['voided_by'] == accountant
    assert c.post(f"/v1/organizations/{org}/cashbook/{wrong['id']}/void", headers=h(owner),
                  json={'reason': 'twice'}).status_code == 409
    assert c.post(f"/v1/organizations/{org}/cashbook/{wrong['id']}/void", headers=h(owner),
                  json={'reason': ''}).status_code == 422
    assert book(org, owner).json()['totals']['CZK']['expense'] == '500.00'
    every = book(org, owner, include_voided='true').json()['items']
    assert {(e['amount'], e['voided']) for e in every} == {('5000.00', True), ('500.00', False)}
    audit = [e['event'] for e in c.get(f'/v1/organizations/{org}/audit', headers=h(owner)).json()]
    assert 'cashbook.entry_voided' in audit and audit.count('cashbook.entry_created') == 2


def test_cash_over_the_legal_limit_is_flagged_per_day_and_counterparty():
    owner, _, _, org = company()
    first = entry(org, owner, method='cash', amount='200000', counterparty='Synthetic Auto s.r.o.', category='equipment')
    assert first.json()['findings'] == []
    second = entry(org, owner, method='cash', amount='70000.01', counterparty='synthetic auto S.R.O.',
                   category='equipment').json()
    assert second['findings'][0]['code'] == 'cash_limit_exceeded'
    assert second['findings'][0]['total'] == '270000.01'
    assert second['findings'][0]['reference'] == '§ 4 zákona č. 254/2004 Sb.'
    # Exactly the limit, another counterparty, another day or cashless: not flagged.
    entry(org, owner, method='cash', amount='270000', counterparty='Other', category='equipment')
    entry(org, owner, method='cash', amount='100000', counterparty='Synthetic Auto s.r.o.',
          entry_date='2026-10-06', category='equipment')
    entry(org, owner, method='bank', amount='900000', counterparty='Synthetic Auto s.r.o.', category='equipment')
    findings = report(org, owner).json()['findings']
    assert len(findings) == 1 and set(findings[0]['entry_ids']) == {first.json()['id'], second['id']}


def test_report_lists_approved_invoices_not_yet_recorded_as_paid():
    owner, accountant, _, org = company()
    paid = upload(org, owner, b'%PDF-1.4\nPaid').json()['id']
    unpaid = upload(org, owner, b'%PDF-1.4\nUnpaid').json()['id']
    pending = upload(org, owner, b'%PDF-1.4\nPending').json()['id']
    for did in (paid, unpaid, pending):
        record(org, owner, did)
    for did in (paid, unpaid):
        c.post(f'/v1/organizations/{org}/documents/{did}/review', headers=h(accountant), json={'decision': 'approve'})
    entry(org, owner, amount='3208', document_id=paid, counterparty='Synthetic Wholesale s.r.o., Praha')
    body = report(org, owner).json()
    assert [u['document_id'] for u in body['unrecorded_invoices']] == [unpaid]
    assert body['unrecorded_invoices'][0]['total'] == '3208.00'
    assert body['totals']['CZK']['expense'] == '3208.00'
    assert body['basis'] == 'cash' and body['is_tax_return'] is False
    assert report(org, owner, '2026-09').json()['unrecorded_invoices'] == []


def test_only_owner_and_accountant_of_the_company_can_use_the_cashbook():
    owner, _, employee, org = company()
    made = entry(org, owner).json()
    stranger = user('Cashbook stranger')
    other_owner, _, _, other_org = company()
    for who in (employee, stranger):
        assert entry(org, who).status_code == 403
        assert book(org, who).status_code == 403
        assert report(org, who).status_code == 403
    assert c.post(f"/v1/organizations/{other_org}/cashbook/{made['id']}/void", headers=h(other_owner),
                  json={'reason': 'not mine'}).status_code == 404
    assert book(other_org, other_owner).json()['items'] == []


def test_future_dates_follow_the_prague_calendar(monkeypatch):
    owner, _, _, org = company()
    # 00:30 in Prague on 6 October is still 5 October on a UTC server.
    monkeypatch.setattr(cashbook, 'today_prague', lambda: '2026-10-06')
    assert entry(org, owner, entry_date='2026-10-06').status_code == 201
    assert entry(org, owner, entry_date='2026-10-07').status_code == 422


def test_a_retried_submission_is_recorded_once():
    owner, accountant, _, org = company()
    key = str(uuid4())
    first = entry(org, owner, key=key, amount='750')
    again = entry(org, owner, key=key, amount='750')
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()['id'] == first.json()['id'] and 'request_hash' not in again.json()
    assert entry(org, owner, key=key, amount='751').status_code == 409
    assert entry(org, accountant, key=key, amount='751').status_code == 201  # keys are per user
    assert book(org, owner).json()['totals']['CZK']['expense'] == '1501.00'
    audit = [e['event'] for e in c.get(f'/v1/organizations/{org}/audit', headers=h(owner)).json()]
    assert audit.count('cashbook.entry_created') == 2
    missing = c.post(f'/v1/organizations/{org}/cashbook', headers=h(owner),
                     json={'kind': 'expense', 'entry_date': '2026-10-05', 'amount': '1',
                           'method': 'bank', 'category': 'goods'})
    assert missing.status_code == 422
