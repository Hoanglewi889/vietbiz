"""CR-10: QR payment on issued invoices, VAT threshold tracker, unanswered shop messages.
Synthetic data only."""
from uuid import uuid4

from app.invoicing import spayd
from app.portfolio import reply_times
from test_api import c, h
from test_invoicing import draft, issue, payer_company, profile, url
from test_portfolio import company, task, user


def issued(org, who, **changes):
    iid = draft(org, who, **changes).json()['id']
    body = issue(org, who, iid)
    assert body.status_code == 200, body.text
    return body.json()


def test_issued_bank_invoice_has_a_qr_payment_with_the_variable_symbol():
    owner, accountant, employee, org = payer_company()
    profile(org, owner, legal_name='Synthetic Bistro Žižkov * s.r.o.')
    pending = draft(org, owner).json()
    assert c.get(url(org, f"/invoices/{pending['id']}/payment-qr"), headers=h(owner)).status_code == 409
    invoice = issued(org, owner)
    r = c.get(url(org, f"/invoices/{invoice['id']}/payment-qr"), headers=h(accountant))
    assert r.status_code == 200
    body = r.json()
    assert body['spayd'] == ('SPD*1.0*ACC:CZ6508000000192000145399*AM:464.56*CC:CZK*DT:20261103*X-VS:'
                             f"{invoice['variable_symbol']}*RN:Synthetic Bistro Zizkov s.r.o.*"
                             f"MSG:Faktura {invoice['number']}")
    assert body['image'].startswith('data:image/svg+xml')
    assert c.get(url(org, f"/invoices/{invoice['id']}/payment-qr"), headers=h(employee)).status_code == 403
    cash = issued(org, owner, payment_method='cash')
    assert c.get(url(org, f"/invoices/{cash['id']}/payment-qr"), headers=h(owner)).status_code == 409


def test_spayd_needs_an_iban_and_something_to_pay():
    invoice = {'status': 'issued', 'number': '2026-0001', 'variable_symbol': '20260001',
               'supplier': {'legal_name': 'X', 'iban': None},
               'content': {'payment_method': 'bank', 'due_date': '2026-11-03'},
               'totals': {'total': '100.00', 'currency': 'CZK'}}
    assert spayd(invoice) is None
    invoice['supplier']['iban'] = 'CZ65 0800 0000 1920 0014 5399'
    assert spayd(invoice).startswith('SPD*1.0*ACC:CZ6508000000192000145399*AM:100.00*')
    invoice['totals']['total'] = '0.00'
    assert spayd(invoice) is None


def cash_entry(org, who, amount, method='cash', category='sales', entry_date='2026-03-02', currency='CZK'):
    r = c.post(f'/v1/organizations/{org}/cashbook', headers={**h(who), 'Idempotency-Key': str(uuid4())},
               json={'kind': 'income', 'entry_date': entry_date, 'amount': amount, 'method': method,
                     'category': category, 'currency': currency})
    assert r.status_code == 201, r.text


def test_vat_threshold_counts_invoices_and_counter_sales_but_not_bank_income():
    owner, accountant, _, org = payer_company()
    profile(org, owner, dic='', vat_payer=False)
    plain = [{**line, 'vat_rate': None, 'unit_price': '500000', 'quantity': '1'} for line in
             [{'description': 'Synthetic catering', 'unit': 'ks'}]]
    issued(org, owner, lines=plain, supply_date='2026-02-10', issue_date='2026-02-10', due_date='2026-02-24')
    issued(org, owner, lines=plain, supply_date='2025-12-30', issue_date='2026-01-05', due_date='2026-01-19')
    cash_entry(org, owner, '800000.00')
    cash_entry(org, owner, '300000.00', method='card', category='services')
    cash_entry(org, owner, '500000.00', method='bank')
    cash_entry(org, owner, '999.00', category='other')
    cash_entry(org, owner, '1000.00', currency='EUR')
    body = c.get(url(org, '/vat-threshold?year=2026'), headers=h(accountant)).json()
    assert (body['invoiced'], body['cash_and_card_sales'], body['bank_income_not_added'],
            body['eur_income_not_added']) == ('500000.00', '1100000.00', '500000.00', '1000.00')
    assert body['estimate'] == '1600000.00' and body['status'] == 'watch' and body['share'] == '0.800'
    assert body['applies'] is True and body['vat_payer'] is False
    cash_entry(org, owner, '500000.00')
    assert c.get(url(org, '/vat-threshold?year=2026'), headers=h(owner)).json()['status'] == 'over_next_year'
    cash_entry(org, owner, '436501.00')
    assert c.get(url(org, '/vat-threshold?year=2026'), headers=h(owner)).json()['status'] == 'over_immediate'
    assert c.get(url(org, '/vat-threshold?year=2025'), headers=h(owner)).json()['invoiced'] == '500000.00'
    # A VAT payer has nothing to track.
    profile(org, owner)
    assert c.get(url(org, '/vat-threshold'), headers=h(owner)).json()['applies'] is False


def row(org, task_id, at, role, status='OPEN'):
    return {'organization_id': org, 'task_id': task_id, 'created_at': at, 'role': role, 'status': status}


def test_reply_times_track_the_oldest_waiting_message_and_the_median_reply():
    rows = [
        row('a', 't1', '2026-11-01T08:00:00+00:00', 'owner'),
        row('a', 't1', '2026-11-01T08:30:00+00:00', 'employee'),  # same wait, not a new one
        row('a', 't1', '2026-11-01T10:00:00+00:00', 'accountant'),  # 120 min
        row('a', 't2', '2026-11-02T09:00:00+00:00', 'owner'),
        row('a', 't2', '2026-11-02T09:20:00+00:00', 'accountant'),  # 20 min
        row('a', 't2', '2026-11-05T07:00:00+00:00', 'owner'),  # waiting
        row('a', 't3', '2026-11-04T07:00:00+00:00', 'owner', status='DONE'),  # closed: not waiting
        row('a', 't4', '2026-09-01T07:00:00+00:00', 'owner'),
        row('a', 't4', '2026-09-01T17:00:00+00:00', 'accountant'),  # older than 30 days
    ]
    assert reply_times(rows, '2026-11-09') == {'a': {'unanswered_messages': 1,
                                                     'oldest_unanswered_at': '2026-11-05T07:00:00+00:00',
                                                     'median_reply_minutes': 70}}


def test_portfolio_shows_waiting_shop_messages_and_the_vat_threshold():
    accountant, owner = user('Reply accountant'), user('Reply owner')
    org = company('Synthetic Nails Reply', owner, accountant)
    tid = task(org, accountant).json()['id']

    def say(who, text, visibility='client'):
        r = c.post(f'/v1/organizations/{org}/tasks/{tid}/comments', json={'body': text, 'visibility': visibility},
                   headers={**h(who), 'Idempotency-Key': str(uuid4())})
        assert r.status_code == 201, r.text

    say(owner, 'Synthetic: faktura chybí')
    say(accountant, 'Synthetic internal note', visibility='accountant')  # not a reply to the shop
    item = next(i for i in c.get('/v1/portfolio', headers=h(accountant)).json()['items'] if i['organization_id'] == org)
    assert item['unanswered_messages'] == 1 and item['oldest_unanswered_at'] is not None
    assert item['vat_threshold'] is None  # payer status unknown: no profile yet
    say(accountant, 'Synthetic: díky, doplním')
    c.put(f'/v1/organizations/{org}/client-profile', headers=h(owner),
          json={'legal_form': 'osvc', 'industry': 'nails', 'vat_status': 'none', 'has_employees': False,
                'osvc_activity': 'main', 'tax_adviser': False})
    item = next(i for i in c.get('/v1/portfolio', headers=h(accountant)).json()['items'] if i['organization_id'] == org)
    assert item['unanswered_messages'] == 0 and item['median_reply_minutes'] == 0
    assert item['vat_threshold'] == 'ok'


# Codex review, PR #15 ---------------------------------------------------------

def test_a_card_paid_invoice_recorded_in_the_cashbook_is_not_counted_twice():
    owner, accountant, _, org = payer_company()
    profile(org, owner, dic='', vat_payer=False)
    big = [{'description': 'Synthetic catering', 'unit': 'ks', 'quantity': '1', 'unit_price': '1100000',
            'vat_rate': None}]
    issued(org, owner, lines=big, payment_method='card', supply_date='2026-02-10', issue_date='2026-02-10',
           due_date='2026-02-10')
    cash_entry(org, owner, '1100000.00', method='card')
    body = c.get(url(org, '/vat-threshold?year=2026'), headers=h(accountant)).json()
    assert (body['estimate'], body['estimate_high']) == ('1100000.00', '2200000.00')
    assert (body['status'], body['status_high']) == ('ok', 'over_next_year')
    assert body['invoiced_cash_and_card'] == '1100000.00'
