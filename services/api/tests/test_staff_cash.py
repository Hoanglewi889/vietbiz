"""CR-12 staff, shifts, tips, daily cash close, leakage signals and weekly cash flow.
Synthetic people and amounts only."""
from uuid import uuid4

import app.cash_control as cash_control
import app.staff as staff_module
from test_api import c, h
from test_archive import company
from test_cashbook import entry


def url(org, path):
    return f'/v1/organizations/{org}{path}'


def person(org, who, **changes):
    body = {'display_name': 'Synthetic Lan', 'job': 'nehtová technička', 'hourly_rate': '180', **changes}
    r = c.post(url(org, '/staff'), headers=h(who), json=body)
    assert r.status_code == 201, r.text
    return r.json()


def shift(org, who, staff_id, key=None, **changes):
    body = {'staff_id': staff_id, 'work_date': '2026-10-05', 'start_time': '09:00', 'end_time': '17:30',
            'break_minutes': 30, 'tips': '250', **changes}
    return c.post(url(org, '/shifts'), headers={**h(who), 'Idempotency-Key': key or str(uuid4())}, json=body)


def period(org, who, start='2026-10-01', end='2026-10-31'):
    return c.get(url(org, '/shifts'), headers=h(who), params={'from': start, 'to': end})


def test_staff_are_kept_minimal_and_edited_with_a_version():
    owner, accountant, employee, org = company()
    assert c.post(url(org, '/staff'), headers=h(employee), json={'display_name': 'X'}).status_code == 403
    lan = person(org, owner, display_name='  Synthetic   Lan ')
    assert lan == {'id': lan['id'], 'display_name': 'Synthetic Lan', 'job': 'nehtová technička',
                   'hourly_rate': '180.00', 'minor': False, 'active': True, 'version': 1,
                   'updated_at': lan['updated_at']}
    assert c.post(url(org, '/staff'), headers=h(owner), json={'display_name': 'Y', 'birth_number': '1'}).status_code == 422
    edit = {'display_name': 'Synthetic Lan', 'hourly_rate': '190', 'active': True}
    assert c.put(url(org, f"/staff/{lan['id']}"), headers=h(owner), json=edit).status_code == 422
    assert c.put(url(org, f"/staff/{lan['id']}"), headers=h(accountant),
                 json={**edit, 'expected_version': 1}).json()['hourly_rate'] == '190.00'
    assert c.put(url(org, f"/staff/{lan['id']}"), headers=h(owner), json={**edit, 'expected_version': 1}).status_code == 409
    _, _, _, other = company()
    assert c.put(url(other, f"/staff/{lan['id']}"), headers=h(owner), json={**edit, 'expected_version': 2}).status_code == 403


def test_shifts_sum_hours_cost_and_tips_and_are_idempotent(monkeypatch):
    monkeypatch.setattr(staff_module, 'today_prague', lambda: '2026-10-31')
    owner, _, employee, org = company()
    lan, hoa = person(org, owner)['id'], person(org, owner, display_name='Synthetic Hoa', hourly_rate=None)['id']
    key = str(uuid4())
    first = shift(org, owner, lan, key=key)
    assert first.status_code == 201
    assert shift(org, owner, lan, key=key).status_code == 200  # a retried submission, not a second shift
    assert shift(org, owner, lan, key=key, tips='999').status_code == 409
    assert shift(org, employee, lan).status_code == 403
    assert shift(org, owner, 'not-a-person').status_code == 422
    assert shift(org, owner, lan, work_date='2026-11-01').status_code == 422  # not worked yet
    assert shift(org, owner, lan, start_time='09:00', end_time='09:00').status_code == 422
    assert shift(org, owner, lan, work_date='2026-10-06', start_time='22:00', end_time='06:00', break_minutes=30,
                 tips='0').status_code == 201  # overnight
    shift(org, owner, hoa, start_time='10:00', end_time='14:00', break_minutes=0, tips='80.5')
    voided = shift(org, owner, hoa, work_date='2026-10-07').json()
    assert c.post(url(org, f"/shifts/{voided['id']}/void"), headers=h(owner), json={'reason': 'zadáno omylem'}
                  ).status_code == 200
    body = period(org, owner).json()
    by = {s['display_name']: s for s in body['summary']}
    # 8 h on the 5th + 7.5 h overnight on the 6th = 15.5 h × 180
    assert (by['Synthetic Lan']['minutes'], by['Synthetic Lan']['labour_cost'], by['Synthetic Lan']['tips']) == (
        930, '2790.00', '250.00')
    assert (by['Synthetic Hoa']['minutes'], by['Synthetic Hoa']['labour_cost'], by['Synthetic Hoa']['tips']) == (
        240, None, '80.50')
    assert body['totals'] == {'minutes': 1170, 'labour_cost': '2790.00', 'tips': '330.50',
                              'unpriced_staff': ['Synthetic Hoa']}
    assert period(org, owner, '2026-10-01', '2026-12-31').status_code == 422


def test_labour_code_prompts_long_shift_missing_break_short_rest_and_overlap(monkeypatch):
    monkeypatch.setattr(staff_module, 'today_prague', lambda: '2026-10-31')
    owner, _, _, org = company()
    adult, minor = person(org, owner)['id'], person(org, owner, display_name='Synthetic Minh', minor=True)['id']
    long = shift(org, owner, adult, work_date='2026-10-10', start_time='07:00', end_time='20:30', break_minutes=30).json()
    early = shift(org, owner, adult, work_date='2026-10-11', start_time='06:00', end_time='12:00', break_minutes=0).json()
    clash = shift(org, owner, adult, work_date='2026-10-11', start_time='11:00', end_time='13:00', break_minutes=0).json()
    teen = shift(org, owner, minor, work_date='2026-10-10', start_time='09:00', end_time='14:00', break_minutes=0).json()
    fine = shift(org, owner, minor, work_date='2026-10-12', start_time='09:00', end_time='13:00', break_minutes=0).json()
    findings = {s['id']: {f['code'] for f in s['findings']} for s in period(org, owner).json()['items']}
    assert findings[long['id']] == {'shift_too_long'}  # 13 h of work
    assert findings[early['id']] == {'rest_too_short'}  # 9.5 h after the long shift; 6 h exactly needs no break
    assert findings[clash['id']] == {'shift_overlap'}
    assert findings[teen['id']] == {'break_missing'}  # 5 h for a person under 18
    assert findings[fine['id']] == set()


def test_daily_close_shows_shortage_missing_closes_and_undocumented_spending(monkeypatch):
    monkeypatch.setattr(cash_control, 'today_prague', lambda: '2026-10-31')
    owner, accountant, employee, org = company()
    entry(org, owner, kind='income', method='cash', category='sales', amount='8000', entry_date='2026-10-05')
    entry(org, owner, kind='expense', method='cash', category='goods', amount='1200', entry_date='2026-10-05')
    entry(org, owner, kind='income', method='cash', category='sales', amount='5000', entry_date='2026-10-06')
    entry(org, owner, kind='expense', method='card', category='goods', amount='450', entry_date='2026-10-06')
    entry(org, owner, kind='income', method='card', category='sales', amount='3000', entry_date='2026-10-07')

    def close(day, who=owner, **body):
        return c.put(url(org, f'/cash-closes/{day}'), headers=h(who),
                     json={'opening_float': '2000', 'counted_cash': '8500', **body})

    assert close('2026-10-05', employee).status_code == 403
    assert close('2026-11-01').status_code == 422
    first = close('2026-10-05').json()
    # expected 2000 + 8000 − 1200 = 8800; counted 8500
    assert (first['expected_cash'], first['difference'], first['version']) == ('8800.00', '-300.00', 1)
    assert close('2026-10-05').status_code == 409  # a second close must name the version it recounts
    recount = close('2026-10-05', accountant, counted_cash='8800', expected_version=1).json()
    assert (recount['difference'], recount['version']) == ('0.00', 2)
    assert close('2026-10-05', counted_cash='8000', expected_version=1).status_code == 409
    close('2026-10-05', counted_cash='8650', expected_version=2)
    body = c.get(url(org, '/cash-control'), headers=h(accountant), params={'month': '2026-10'}).json()
    assert body['totals'] == {'shortage': '-150.00', 'surplus': '0.00', 'closed_days': 1,
                              'days_without_close': ['2026-10-06']}  # card-only days need no count
    assert [(e['entry_date'], e['amount']) for e in body['undocumented_expenses']] == [
        ('2026-10-05', '1200.00')]  # the 450 card purchase is under the threshold
    assert body['suggested_opening_float'] == '8650.00'
    # A cashbook change after counting is shown, not folded silently into the difference.
    entry(org, owner, kind='expense', method='cash', category='other', amount='100', entry_date='2026-10-05')
    day = next(d for d in c.get(url(org, '/cash-control'), headers=h(owner), params={'month': '2026-10'}).json()['days']
               if d['date'] == '2026-10-05')
    assert day['changed_since_close'] is True and day['close']['difference'] == '-150.00'


def test_weekly_cash_flow_takes_bank_money_from_statements_when_a_week_has_them(monkeypatch):
    monkeypatch.setattr(cash_control, 'today_prague', lambda: '2026-11-08')  # a Sunday
    owner, _, _, org = company()
    entry(org, owner, kind='income', method='cash', category='sales', amount='1000', entry_date='2026-10-27')
    entry(org, owner, kind='income', method='bank', category='sales', amount='500', entry_date='2026-10-28')
    entry(org, owner, kind='income', method='bank', category='sales', amount='700', entry_date='2026-11-03')
    entry(org, owner, kind='expense', method='card', category='goods', amount='300', entry_date='2026-11-04')
    statement = ('Datum;Objem;Měna;Název protiúčtu\n04.11.2026;900,00;CZK;Synthetic\n05.11.2026;-200,00;CZK;Fee\n')
    c.post(url(org, '/bank/imports'), headers=h(owner), files={'file': ('v.csv', statement.encode(), 'text/csv')})
    weeks = c.get(url(org, '/cash-flow'), headers=h(owner), params={'weeks': 2}).json()['weeks']
    assert [w['week_start'] for w in weeks] == ['2026-10-26', '2026-11-02']
    assert (weeks[0]['bank_source'], weeks[0]['in'], weeks[0]['net']) == ('cashbook', '1500.00', '1500.00')
    # The statement replaces the cashbook's bank entries for that week: 900 in, 200 out, plus 300 by card.
    assert (weeks[1]['bank_source'], weeks[1]['in'], weeks[1]['out'], weeks[1]['net']) == (
        'statement', '900.00', '500.00', '400.00')
