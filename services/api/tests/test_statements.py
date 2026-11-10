"""CR-13 statement register: original files, account periods and balances, gaps, monthly coverage,
card payouts against card sales, and the portfolio flag. Synthetic statements only."""
import app.bank as bank
from test_api import c, h
from test_bank import gpc_075
from test_cashbook import entry
from test_invoicing import payer_company, url
from test_portfolio import company, user


def header(old_date, old_hal, new_hal, number, day, account='1234567890', old_sign='+', new_sign='+'):
    line = ('074' + account.zfill(16) + 'SYNTHETIC UCET'.ljust(20) + old_date + str(old_hal).zfill(14) + old_sign
            + str(new_hal).zfill(14) + new_sign + '0' * 14 + '0' + '0' * 14 + '0' + str(number).zfill(3) + day
            + ' ' * 14)
    assert len(line) == 128
    return line


def statement(*lines):
    return ('\r\n'.join(lines) + '\r\n').encode('cp1250')


def send(org, who, content, name='vypis.gpc'):
    return c.post(url(org, '/bank/imports'), headers=h(who), files={'file': (name, content, 'text/plain')})


def test_gpc_header_gives_account_period_balances_and_the_file_is_kept():
    owner, accountant, employee, org = payer_company()
    october = statement(header('300926', 100000, 150000, 10, '311026'), gpc_075(50000, '2', ref='1', day='151026'))
    r = send(org, owner, october)
    assert r.status_code == 201
    assert {k: r.json()[k] for k in ('account', 'period_from', 'period_to', 'opening_balance', 'closing_balance',
                                     'statement_no')} == {
        'account': '1234567890', 'period_from': '2026-10-01', 'period_to': '2026-10-31',
        'opening_balance': '1000.00', 'closing_balance': '1500.00', 'statement_no': 10}
    listed = c.get(url(org, '/bank/imports'), headers=h(accountant)).json()
    assert [i['period_to'] for i in listed['items']] == ['2026-10-31'] and listed['breaks'] == []
    download = c.get(url(org, f"/bank/imports/{r.json()['import_id']}/file"), headers=h(accountant))
    assert download.status_code == 200 and download.content == october
    assert download.headers['x-content-type-options'] == 'nosniff'
    assert c.get(url(org, '/bank/imports'), headers=h(employee)).status_code == 403
    owner_b, _, _, org_b = payer_company()
    assert c.get(url(org_b, f"/bank/imports/{r.json()['import_id']}/file"), headers=h(owner_b)).status_code == 404


def test_gaps_and_balances_that_do_not_follow_on_are_reported():
    owner, _, _, org = payer_company()
    send(org, owner, statement(header('310826', 0, 100000, 8, '300926')))
    send(org, owner, statement(header('300926', 100000, 150000, 9, '311026')))      # follows on
    send(org, owner, statement(header('301126', 150000, 160000, 11, '311226')))     # November missing
    send(org, owner, statement(header('311226', 170000, 180000, 12, '310127')))     # 1 600 ≠ 1 700
    breaks = c.get(url(org, '/bank/imports'), headers=h(owner)).json()['breaks']
    assert [(b['kind'], b.get('missing_from'), b.get('missing_to'), b.get('closing'), b.get('opening'))
            for b in breaks] == [('gap', '2026-11-01', '2026-11-30', None, None),
                                 ('balance', None, None, '1600.00', '1700.00')]


def test_month_coverage_counts_up_to_today(monkeypatch):
    monkeypatch.setattr(bank, 'today_prague', lambda: '2026-11-10')
    owner, _, _, org = payer_company()
    send(org, owner, statement(header('310826', 0, 1, 1, '300926')))
    send(org, owner, statement(header('300926', 1, 2, 2, '151026')))
    send(org, owner, statement(header('311026', 2, 3, 3, '101126')))
    accounts = c.get(url(org, '/bank/coverage'), headers=h(owner), params={'months': 4}).json()['accounts']
    assert [(m['month'], m['state'], m['missing_days']) for m in accounts[0]['months']] == [
        ('2026-09', 'covered', 0), ('2026-10', 'partial', 16), ('2026-11', 'covered', 0)]  # 16–31 Oct
    assert accounts[0]['through'] == '2026-11-10'


def test_csv_metadata_gives_the_period_and_balances():
    owner, _, _, org = payer_company()
    text = ('"accountId";"2000000000"\n"bankId";"2010"\n"openingBalance";"1000,00"\n"closingBalance";"1200,00"\n'
            '"dateStart";"01.10.2026"\n"dateEnd";"31.10.2026"\n\n'
            '"Datum";"Objem";"Měna";"Název protiúčtu"\n"05.10.2026";"200,00";"CZK";"Synthetic"\n')
    body = send(org, owner, text.encode(), name='vypis.csv').json()
    assert (body['account'], body['period_from'], body['period_to'], body['opening_balance'],
            body['closing_balance']) == ('2000000000/2010', '2026-10-01', '2026-10-31', '1000.00', '1200.00')


def test_card_payouts_are_marked_and_compared_with_card_sales():
    owner, accountant, _, org = payer_company()
    entry(org, owner, kind='income', method='card', category='sales', amount='10000', entry_date='2026-10-05')
    entry(org, owner, kind='income', method='card', category='sales', amount='5000', entry_date='2026-10-20')
    send(org, owner, statement(header('300926', 0, 0, 1, '311026'),
                               gpc_075(985000, '2', ref='1', name='Synthetic Payments', day='071026'),
                               gpc_075(492000, '2', ref='2', name='Synthetic Payments', day='221026'),
                               gpc_075(9900, '1', ref='3', day='311026')))
    items = {i['amount']: i for i in c.get(url(org, '/bank/transactions'), headers=h(owner)).json()['items']}

    def ignore(tx, purpose):
        return c.post(url(org, f"/bank/transactions/{tx['id']}/ignore"), headers=h(accountant),
                      json={'expected_version': tx['version'], 'purpose': purpose})

    assert ignore(items['9850.00'], 'card_payout').json()['purpose'] == 'card_payout'
    ignore(items['4920.00'], 'card_payout')
    fee = ignore(items['-99.00'], 'bank_fee').json()
    assert ignore(items['-99.00'] | {'version': fee['version']}, 'pizza').status_code == 422
    report = c.get(url(org, '/bank/card-payouts'), headers=h(owner), params={'month': '2026-10'}).json()
    assert (report['card_sales'], report['payouts'], report['difference'], report['difference_share']) == (
        '15000.00', '14770.00', '230.00', '0.0153')
    # Unmatching clears the purpose with the decision.
    back = c.post(url(org, f"/bank/transactions/{fee['id']}/unmatch"), headers=h(owner),
                  json={'expected_version': fee['version']}).json()
    assert (back['status'], back['purpose']) == ('unmatched', None)


def test_portfolio_flags_a_company_missing_last_months_statement(monkeypatch):
    monkeypatch.setattr(bank, 'today_prague', lambda: '2026-11-10')
    import app.portfolio as portfolio
    monkeypatch.setattr(portfolio, 'today_prague', lambda: '2026-11-10')
    accountant, owner_a, owner_b, owner_c = (user(n) for n in ('Stmt accountant', 'Stmt A', 'Stmt B', 'Stmt C'))
    complete, behind, never = (company(n, o, accountant) for n, o in
                               (('Synthetic Complete', owner_a), ('Synthetic Behind', owner_b),
                                ('Synthetic Never', owner_c)))
    send(complete, owner_a, statement(header('300926', 0, 0, 1, '311026')))
    send(complete, owner_a, statement(header('311026', 0, 0, 2, '301126')))
    send(behind, owner_b, statement(header('300926', 0, 0, 1, '151026')))
    rows = {i['organization_id']: i for i in c.get('/v1/portfolio', headers=h(accountant)).json()['items']}
    assert (rows[complete]['statements_through'], rows[complete]['statement_missing_month']) == ('2026-11-30', None)
    assert (rows[behind]['statements_through'], rows[behind]['statement_missing_month']) == ('2026-10-15', '2026-10')
    assert (rows[never]['statements_through'], rows[never]['statement_missing_month']) == (None, None)


def test_a_header_whose_period_runs_backwards_falls_back_to_the_movements():
    owner, _, _, org = payer_company()
    body = send(org, owner, statement(header('301126', 0, 0, 3, '091126'), gpc_075(100, '2', ref='1', day='051126'))).json()
    assert (body['period_from'], body['period_to']) == ('2026-11-05', '2026-11-09')


def test_a_czech_or_vietnamese_file_name_downloads_with_an_encoded_header():
    """Codex review, PR #19: a non-Latin-1 name must not turn the download into HTTP 500."""
    owner, _, _, org = payer_company()
    content = statement(header('300926', 0, 0, 1, '311026'))
    imported = send(org, owner, content, name='výpis-říjen sao kê.gpc').json()
    r = c.get(url(org, f"/bank/imports/{imported['import_id']}/file"), headers=h(owner))
    assert r.status_code == 200 and r.content == content
    assert r.headers['content-disposition'] == (
        'attachment; filename="vypis-rijensaoke.gpc"; '
        "filename*=UTF-8''v%C3%BDpis-%C5%99%C3%ADjen%20sao%20k%C3%AA.gpc")
