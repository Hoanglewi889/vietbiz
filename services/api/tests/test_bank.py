"""CR-11 bank statements, payment matching, reminders and duplicate received invoices.
Synthetic statements and companies only."""
from decimal import Decimal

import pytest

import app.bank as bank
from test_api import c, h
from test_archive import FIELDS, record, upload
from test_invoicing import draft, issue, payer_company, url


def gpc_075(amount_hal, code, vs='', counter='', bank_code='0800', ref='1', name='', day='051126',
            account='1234567890', currency='0203'):
    line = ('075' + account.zfill(16) + counter.zfill(16) + ref.zfill(13) + str(amount_hal).zfill(12) + code
            + vs.zfill(10) + (bank_code + '0308').ljust(10, '0') + '0' * 10 + '000000' + name.ljust(20)[:20]
            + '0' + currency + day)
    assert len(line) == 128
    return line


def gpc(*movements, day='061126'):
    header = ('074' + '1234567890'.zfill(16) + 'SYNTHETIC UCET'.ljust(20) + '011126' + '0' * 14 + '+'
              + '0' * 14 + '+' + '0' * 14 + '0' + '0' * 14 + '0' + '001' + day + ' ' * 14)
    assert len(header) == 128
    return ('\r\n'.join([header, *movements]) + '\r\n').encode('cp1250')


def issued(org, who, **changes):
    iid = draft(org, who, **changes).json()['id']
    return issue(org, who, iid).json()


def send(org, who, content, name='vypis.gpc'):
    return c.post(url(org, '/bank/imports'), headers=h(who), files={'file': (name, content, 'text/plain')})


def movements(org, who, **params):
    return c.get(url(org, '/bank/transactions'), headers=h(who), params=params).json()


def test_gpc_records_give_signed_amounts_symbols_and_counter_accounts():
    rows = bank.parse_gpc(gpc(gpc_075(46456, '2', vs='20260001', counter='19', name='Synthetic Customer'),
                              gpc_075(12000, '1', counter='2001', bank_code='2010', ref='2'),
                              gpc_075(500, '4', ref='3'), gpc_075(700, '5', ref='4')))
    assert [str(r['amount']) for r in rows] == ['464.56', '-120.00', '5.00', '-7.00']
    first = rows[0]
    assert (first['vs'], first['counter_account'], first['booked_on'], first['currency'], first['counter_name']) == (
        '20260001', '19/0800', '2026-11-05', 'CZK', 'Synthetic Customer')
    with pytest.raises(bank.StatementError):
        bank.parse_gpc(gpc(gpc_075(1, '9')))


def test_bank_csv_is_found_by_its_header_even_after_metadata_and_in_cp1250():
    text = ('"accountId";"2000000000"\n"bankId";"2010"\n\n'
            '"ID pohybu";"Datum";"Objem";"Měna";"Protiúčet";"Kód banky";"Název protiúčtu";"VS";"Zpráva pro příjemce"\n'
            '"111";"05.11.2026";"1 200,50";"CZK";"19";"0800";"Synthetic Odběratel";"0020260001";"Faktura"\n'
            '"112";"06.11.2026";"-99,00";"CZK";"";"";"Poplatek";"";""\n')
    rows = bank.parse_csv(text.encode('cp1250'))
    assert [(r['bank_ref'], r['booked_on'], str(r['amount']), r['vs'], r['counter_account']) for r in rows] == [
        ('111', '2026-11-05', '1200.50', '20260001', '19/0800'), ('112', '2026-11-06', '-99.00', None, None)]
    with pytest.raises(bank.StatementError):
        bank.parse_csv(b'a;b;c\n1;2;3\n')


def test_import_matches_full_and_partial_payments_and_leaves_the_rest_to_a_person():
    owner, accountant, employee, org = payer_company()
    full, part, over = (issued(org, owner) for _ in range(3))
    supplier = upload(org, owner, b'%PDF-1.4\nSynthetic bill').json()['id']
    record(org, owner, supplier, total='3208.00')
    statement = gpc(
        gpc_075(46456, '2', vs=full['variable_symbol'], counter='19', ref='11'),
        gpc_075(20000, '2', vs=part['variable_symbol'], counter='19', ref='12'),
        gpc_075(50000, '2', vs=over['variable_symbol'], counter='19', ref='13'),
        gpc_075(46456, '2', counter='27', ref='14'),
        gpc_075(320800, '1', counter='1', ref='15'),
    )
    assert send(org, employee, statement).status_code == 403
    r = send(org, accountant, statement)
    assert r.status_code == 201, r.text
    assert r.json() | {'import_id': None} == {'import_id': None, 'format': 'gpc', 'rows': 5, 'added': 5,
                                              'already_known': 0, 'auto_matched': 2}
    assert send(org, owner, statement).status_code == 409
    # An overlapping statement adds only what is new.
    again = send(org, owner, gpc(gpc_075(46456, '2', vs=full['variable_symbol'], counter='19', ref='11'),
                                 gpc_075(100, '1', ref='16'), day='071126'))
    assert again.json()['added'] == 1 and again.json()['already_known'] == 1
    pay = {i['id']: i['payment'] for i in c.get(url(org, '/invoices'), headers=h(owner)).json()['items']}
    assert pay[full['id']] == {'paid': '464.56', 'remaining': '0.00', 'state': 'paid'}
    assert pay[part['id']] == {'paid': '200.00', 'remaining': '264.56', 'state': 'partial'}
    assert pay[over['id']]['state'] == 'unpaid'
    body = movements(org, accountant, status='unmatched')
    assert body['counts'] == {'matched': 2, 'unmatched': 4}
    by_amount = {i['amount']: i for i in body['items']}
    assert by_amount['500.00']['suggestions'][0]['issued_invoice_id'] == over['id']  # same VS, too much
    no_vs = by_amount['464.56']['suggestions']
    assert {s['issued_invoice_id'] for s in no_vs} == {over['id']}  # amount equals what is still owed
    assert by_amount['-3208.00']['suggestions'][0]['document_id'] == supplier


def test_manual_match_ignore_and_unmatch_are_versioned_and_scoped():
    owner, accountant, _, org = payer_company()
    invoice = issued(org, owner)
    supplier = upload(org, owner, b'%PDF-1.4\nSynthetic bill 2').json()['id']
    record(org, owner, supplier, total='120.00')
    send(org, owner, gpc(gpc_075(46456, '2', counter='27', ref='21'), gpc_075(12000, '1', ref='22'),
                         gpc_075(1500, '1', ref='23')))
    items = {i['amount']: i for i in movements(org, owner)['items']}
    money_in, money_out, fee = items['464.56'], items['-120.00'], items['-15.00']

    def act(tx, verb, **body):
        return c.post(url(org, f"/bank/transactions/{tx['id']}/{verb}"), headers=h(accountant), json=body)

    assert act(money_in, 'match', expected_version=1, document_id=supplier).status_code == 422
    assert act(money_in, 'match', expected_version=1).status_code == 422
    assert act(money_in, 'match', expected_version=2, issued_invoice_id=invoice['id']).status_code == 409
    matched = act(money_in, 'match', expected_version=1, issued_invoice_id=invoice['id']).json()
    assert matched['status'] == 'matched' and matched['matched_by'] == 'manual' and matched['version'] == 2
    assert act(money_out, 'match', expected_version=1, document_id=supplier).json()['document_id'] == supplier
    assert act(fee, 'ignore', expected_version=1, note='Poplatek banky').json()['status'] == 'ignored'
    assert act(money_in, 'unmatch', expected_version=2).json()['status'] == 'unmatched'
    # Another company's invoice is out of reach.
    owner_b, _, _, org_b = payer_company()
    foreign = issued(org_b, owner_b)
    assert act(money_in, 'match', expected_version=3, issued_invoice_id=foreign['id']).status_code == 404


def test_possible_duplicate_payments_are_flagged_within_three_days():
    rows = [{'id': 'a', 'amount': '-500.00', 'currency': 'CZK', 'counter_account': '1/0800', 'counter_name': None,
             'booked_on': '2026-11-02'},
            {'id': 'b', 'amount': '-500.00', 'currency': 'CZK', 'counter_account': '1/0800', 'counter_name': None,
             'booked_on': '2026-11-04'},
            {'id': 'c', 'amount': '-500.00', 'currency': 'CZK', 'counter_account': '1/0800', 'counter_name': None,
             'booked_on': '2026-11-20'},
            {'id': 'd', 'amount': '-50.00', 'currency': 'CZK', 'counter_account': '1/0800', 'counter_name': None,
             'booked_on': '2026-11-02'},
            {'id': 'e', 'amount': '-50.00', 'currency': 'CZK', 'counter_account': '1/0800', 'counter_name': None,
             'booked_on': '2026-11-02'}]
    assert dict(bank.duplicate_flags(rows)) == {'a': ['b'], 'b': ['a']}


def test_reminders_list_overdue_balances_per_customer_with_a_qr(monkeypatch):
    monkeypatch.setattr(bank, 'today_prague', lambda: '2026-11-20')
    owner, _, _, org = payer_company()
    paid, owed = issued(org, owner), issued(org, owner)
    issued(org, owner, due_date='2026-12-01')  # not due yet
    issued(org, owner, customer_name='Synthetic Other s.r.o.', customer_ico='00000035', payment_method='cash')
    send(org, owner, gpc(gpc_075(46456, '2', vs=paid['variable_symbol'], ref='31'),
                         gpc_075(6456, '2', vs=owed['variable_symbol'], ref='32')))
    body = c.get(url(org, '/reminders'), headers=h(owner)).json()
    first, other = body['groups']
    assert (first['customer_name'], first['stage'], first['days_overdue']) == ('Synthetic Customer a.s.', 'second', 17)
    assert [(i['number'], i['remaining']) for i in first['invoices']] == [(owed['number'], '400.00')]
    assert '*AM:400.00*' in first['invoices'][0]['spayd'] and first['invoices'][0]['qr'].startswith('data:image/svg')
    assert other['invoices'][0]['qr'] is None  # paid in cash: no bank QR
    assert Decimal(first['remaining']) == Decimal('400.00')


def test_received_invoice_with_a_known_number_from_the_same_supplier_is_flagged():
    owner, accountant, _, org = payer_company()
    first = upload(org, owner, b'%PDF-1.4\nOriginal').json()['id']
    record(org, owner, first)
    copy = upload(org, owner, b'%PDF-1.4\nScanned again').json()['id']
    r = c.put(f'/v1/organizations/{org}/documents/{copy}/extraction', headers=h(accountant),
              json={'version': 0, 'fields': {**FIELDS, 'document_number': 'syn 1'}})
    assert [d['document_id'] for d in r.json()['possible_duplicates']] == [first]
    other = upload(org, owner, b'%PDF-1.4\nOther supplier').json()['id']
    r = c.put(f'/v1/organizations/{org}/documents/{other}/extraction', headers=h(accountant),
              json={'version': 0, 'fields': {**FIELDS, 'supplier_vat_id': 'CZ00000009'}})
    assert r.json()['possible_duplicates'] == []
    assert c.get(f'/v1/organizations/{org}/documents/{first}/extraction',
                 headers=h(owner)).json()['possible_duplicates'][0]['document_id'] == copy
    archive = {i['id']: i for i in c.get(f'/v1/organizations/{org}/archive', headers=h(owner)).json()['items']}
    assert archive[first]['possible_duplicates'] == [copy] and archive[other]['possible_duplicates'] == []
    # Rejecting the copy takes it out of the comparison.
    c.post(f'/v1/organizations/{org}/documents/{copy}/review', headers=h(accountant), json={'decision': 'reject'})
    archive = {i['id']: i for i in c.get(f'/v1/organizations/{org}/archive', headers=h(owner)).json()['items']}
    assert archive[first]['possible_duplicates'] == []
