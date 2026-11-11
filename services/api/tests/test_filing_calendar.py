"""CR-8 client profiles and filing calendar. Synthetic companies only.

Expected dates are the published 2026 calendar (sources in app/filing_calendar.py), so a rule
change that breaks them fails here rather than in a client's mailbox.
"""
from datetime import date

import app.filing_calendar as fc
from test_api import c, h
from test_portfolio import company, user


def profile(**overrides):
    base = {'legal_form': 'osvc', 'industry': 'nails', 'vat_status': 'none', 'has_employees': False,
            'osvc_activity': 'main', 'flat_tax_band': None, 'tax_adviser': False, 'health_insurer': None}
    return {**base, **overrides}


def due(items, code):
    return [i['due_date'] for i in items if i['code'] == code]


def test_czech_holidays_include_easter_and_move_deadlines():
    assert fc.easter(2026) == date(2026, 4, 5) and fc.easter(2027) == date(2027, 3, 28)
    assert {date(2026, 4, 3), date(2026, 4, 6), date(2026, 5, 1), date(2026, 12, 24)} <= fc.holidays(2026)
    assert fc.working_day(date(2026, 12, 25)) == date(2026, 12, 28)


def test_monthly_vat_dates_match_the_published_2026_calendar():
    items = fc.deadlines(profile(legal_form='sro', osvc_activity=None, vat_status='monthly'),
                         date(2026, 1, 1), date(2026, 12, 31))
    assert due(items, 'vat_return') == ['2026-01-26', '2026-02-25', '2026-03-25', '2026-04-27', '2026-05-25',
                                        '2026-06-25', '2026-07-27', '2026-08-25', '2026-09-25', '2026-10-26',
                                        '2026-11-25', '2026-12-28']
    assert due(items, 'control_statement') == due(items, 'vat_return')
    december = next(i for i in items if i['code'] == 'vat_return' and i['period'] == '2026-11')
    assert december['moved_from'] == '2026-12-25'
    # A company files corporate tax electronically (data box): 1 May 2026 is a holiday.
    assert due(items, 'corporate_tax_return') == ['2026-05-04']
    assert not due(items, 'income_tax_return') and not due(items, 'flat_tax')


def test_quarterly_vat_company_still_files_control_statement_monthly_but_osvc_quarterly():
    window = (date(2026, 1, 1), date(2026, 6, 30))
    sro = fc.deadlines(profile(legal_form='sro', osvc_activity=None, vat_status='quarterly'), *window)
    osvc = fc.deadlines(profile(vat_status='quarterly'), *window)
    assert [i['period'] for i in sro if i['code'] == 'vat_return'] == ['2025-Q4', '2026-Q1']
    assert len(due(sro, 'control_statement')) == 6
    assert [i['period'] for i in osvc if i['code'] == 'control_statement'] == ['2025-Q4', '2026-Q1']


def test_osvc_annual_return_and_overviews_follow_published_2026_dates():
    window = (date(2026, 1, 1), date(2026, 12, 31))
    own = fc.deadlines(profile(), *window)
    assert due(own, 'income_tax_return') == ['2026-05-04']
    assert due(own, 'social_overview') == ['2026-06-01']
    assert due(own, 'health_overview') == ['2026-06-04']
    adviser = fc.deadlines(profile(tax_adviser=True), *window)
    assert due(adviser, 'income_tax_return') == ['2026-07-01']
    assert due(adviser, 'social_overview') == due(adviser, 'health_overview') == ['2026-08-03']


def test_osvc_advances_carry_the_yearly_minimum_and_no_guess_for_unknown_years():
    items = fc.deadlines(profile(), date(2026, 12, 1), date(2028, 1, 31))
    social = {i['period']: i for i in items if i['code'] == 'social_advance'}
    health = {i['period']: i for i in items if i['code'] == 'health_advance'}
    # From July 2026 the minimum social advance is 5 005 Kč (ČSSZ, official).
    assert social['2026-12']['due_date'] == '2026-12-31' and social['2026-12']['amount']['value'] == '5005'
    assert social['2026-12']['amount']['status'] == 'official'
    assert 'cssz.gov.cz' in social['2026-12']['amount']['source']
    assert social['2027-01']['amount']['value'] == '5281' and health['2027-01']['amount']['value'] == '3488'
    assert health['2026-12']['due_date'] == '2027-01-08'
    assert all(i['amount']['status'] in ('official', 'reported') and i['amount']['source'].startswith('https://')
               for i in social.values() if i['amount'])
    assert social['2028-01']['amount'] is None
    secondary = fc.deadlines(profile(osvc_activity='secondary'), date(2027, 1, 1), date(2027, 1, 31))
    assert next(i for i in secondary if i['code'] == 'social_advance')['amount']['value'] == '1660'
    sec_health = next(i for i in secondary if i['code'] == 'health_advance')
    assert sec_health['conditional'] and sec_health['amount'] is None


def test_flat_tax_replaces_advances_and_annual_return():
    items = fc.deadlines(profile(flat_tax_band=1), date(2026, 1, 1), date(2027, 1, 31))
    assert due(items, 'flat_tax_notice') == ['2026-01-12', '2027-01-11']
    flat = {i['period']: i for i in items if i['code'] == 'flat_tax'}
    assert flat['2026-01']['due_date'] == '2026-01-20' and flat['2026-01']['amount']['value'] == '9984'
    assert flat['2026-06']['amount']['value'] == '9984' and flat['2026-07']['amount']['value'] == '9162'
    assert flat['2027-01']['amount']['value'] == '9662'
    assert flat['2026-06']['due_date'] == '2026-06-22'  # 20 June 2026 is a Saturday
    assert not any(i['code'] in ('social_advance', 'health_advance', 'income_tax_return', 'social_overview')
                   for i in items)


def test_payroll_identified_person_and_eet_start():
    items = fc.deadlines(profile(has_employees=True, vat_status='identified'), date(2026, 12, 1), date(2027, 1, 31))
    assert due(items, 'payroll') == ['2026-12-21', '2027-01-20']
    identified = [i for i in items if i['code'] == 'vat_return_identified']
    assert identified and all(i['conditional'] for i in identified)
    assert not due(items, 'control_statement')
    assert due(items, 'eet_start') == ['2027-01-01']
    online = fc.deadlines(profile(industry='online'), date(2026, 12, 1), date(2027, 1, 31))
    assert not due(online, 'eet_start')


def test_profile_api_validates_versions_and_scope(monkeypatch):
    monkeypatch.setattr(fc, 'today_prague', lambda: '2026-11-09')
    owner, accountant, staff = user('Profile owner'), user('Profile accountant'), user('Profile staff')
    org = company('Synthetic Nails', owner, accountant, staff)
    url = f'/v1/organizations/{org}/client-profile'
    assert c.get(url, headers=h(owner)).json() == {'profile': None}
    assert c.get(url, headers=h(staff)).status_code == 403
    assert c.put(url, json=profile(), headers=h(staff)).status_code == 403
    # Flat tax is closed to VAT payers; s.r.o. has no OSVČ activity type.
    assert c.put(url, json=profile(vat_status='monthly', flat_tax_band=1), headers=h(accountant)).status_code == 422
    assert c.put(url, json=profile(legal_form='sro'), headers=h(accountant)).status_code == 422
    first = c.put(url, json=profile(flat_tax_band=2), headers=h(accountant))
    assert first.status_code == 200 and first.json()['profile']['version'] == 1
    # A second create, or an edit against a stale version, must not overwrite silently.
    assert c.put(url, json=profile(), headers=h(owner)).status_code == 409
    assert c.put(url, json=profile(expected_version=1, health_insurer=' VZP '), headers=h(owner)).json()[
        'profile'] == {**profile(health_insurer='VZP'), 'version': 2,
                       'updated_at': c.get(url, headers=h(owner)).json()['profile']['updated_at']}
    assert c.put(url, json=profile(expected_version=1), headers=h(accountant)).status_code == 409
    calendar_ = c.get(f'/v1/organizations/{org}/deadlines?days=30', headers=h(accountant)).json()
    assert calendar_['from'] == '2026-11-09' and calendar_['to'] == '2026-12-09'
    assert [i['code'] for i in calendar_['items']] == ['social_advance', 'health_advance']
    assert c.get(f'/v1/organizations/{org}/deadlines', headers=h(staff)).status_code == 403
    audit = c.get(f'/v1/organizations/{org}/audit', headers=h(owner)).json()
    assert sum(e['event'] == 'client_profile.updated' for e in audit) == 2


def test_portfolio_calendar_lists_every_company_and_flags_missing_profiles(monkeypatch):
    monkeypatch.setattr(fc, 'today_prague', lambda: '2026-11-09')
    accountant, other = user('Calendar accountant'), user('Other accountant')
    owner_a, owner_b, owner_c = user('Owner A'), user('Owner B'), user('Owner C')
    shop = company('Synthetic Potraviny', owner_a, accountant)
    bistro = company('Synthetic Bistro', owner_b, accountant)
    elsewhere = company('Not mine', owner_c, other)
    for org, body, who in ((shop, profile(industry='grocery', legal_form='sro', osvc_activity=None,
                                          vat_status='monthly', has_employees=True), owner_a),
                           (elsewhere, profile(), owner_c)):
        assert c.put(f'/v1/organizations/{org}/client-profile', json=body, headers=h(who)).status_code == 200
    body = c.get('/v1/deadlines?days=20', headers=h(accountant)).json()
    assert body['profiles_missing'] == [{'organization_id': bistro, 'name': 'Synthetic Bistro'}]
    assert {i['organization_id'] for i in body['items']} == {shop}
    assert [(i['due_date'], i['code']) for i in body['items']] == [
        ('2026-11-20', 'payroll'), ('2026-11-25', 'control_statement'), ('2026-11-25', 'vat_return')]
    rows = {i['organization_id']: i for i in c.get('/v1/portfolio', headers=h(accountant)).json()['items']}
    assert rows[bistro]['profile_missing'] and rows[bistro]['next_deadline'] is None
    assert not rows[shop]['profile_missing']
    assert rows[shop]['next_deadline'] == {'code': 'payroll', 'due_date': '2026-11-20', 'period': '2026-10'}


def test_the_july_2026_cut_applies_from_its_month_on():
    items = fc.deadlines(profile(), date(2026, 6, 1), date(2026, 7, 31))
    social = {i['period']: i['amount'] for i in items if i['code'] == 'social_advance'}
    assert social['2026-06']['value'] == '5720' and social['2026-06']['status'] == 'reported'
    assert social['2026-07']['value'] == '5005' and social['2026-07']['status'] == 'official'
    secondary = fc.deadlines(profile(osvc_activity='secondary'), date(2026, 7, 1), date(2026, 7, 31))
    assert next(i for i in secondary if i['code'] == 'social_advance')['amount']['value'] == '1574'
    band2 = fc.deadlines(profile(flat_tax_band=2), date(2026, 7, 1), date(2026, 7, 31))
    assert next(i for i in band2 if i['code'] == 'flat_tax')['amount']['value'] == '16745'
