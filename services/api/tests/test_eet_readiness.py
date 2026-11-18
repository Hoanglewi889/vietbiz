"""EET 2.0 readiness steps per company (owner request 18.11.2026). Synthetic data only."""
from test_api import c, h
from test_archive import company


def url(org, step=''):
    return f'/v1/organizations/{org}/eet-readiness' + (f'/{step}' if step else '')


def test_steps_start_open_and_everyone_in_the_company_sees_them():
    owner, accountant, employee, org = company()
    for who in (owner, accountant, employee):
        r = c.get(url(org), headers=h(who))
        assert r.status_code == 200
    body = r.json()
    assert [s['step'] for s in body['steps']] == ['applies', 'dis', 'units', 'certificate', 'tool', 'pilot']
    assert body['applies'] and body['remaining'] == [s['step'] for s in body['steps']]


def test_owner_and_accountant_tick_steps_and_see_who_did_it():
    owner, accountant, employee, org = company()
    assert c.put(url(org, 'applies'), headers=h(owner), json={'done': True, 'choice': 'yes'}).status_code == 200
    r = c.put(url(org, 'dis'), headers=h(accountant), json={'done': True})
    assert r.status_code == 200
    steps = {s['step']: s for s in r.json()['steps']}
    assert steps['applies']['choice'] == 'yes' and steps['dis']['done'] and steps['dis']['done_by']
    assert r.json()['remaining'] == ['units', 'certificate', 'tool', 'pilot']
    assert c.put(url(org, 'units'), headers=h(employee), json={'done': True}).status_code == 403
    r = c.put(url(org, 'dis'), headers=h(owner), json={'done': False})
    assert 'dis' in r.json()['remaining']
    events = [e['event'] for e in c.get(f'/v1/organizations/{org}/audit', headers=h(owner)).json()]
    assert events.count('eet.step') == 3


def test_no_steps_left_when_eet_does_not_apply_or_eet_off():
    owner, _, _, org = company()
    for choice in ('no', 'eet_off'):
        r = c.put(url(org, 'applies'), headers=h(owner), json={'done': True, 'choice': choice})
        assert r.json()['applies'] is False and r.json()['remaining'] == []


def test_invalid_steps_and_choices_are_refused():
    owner, _, _, org = company()
    assert c.put(url(org, 'nonsense'), headers=h(owner), json={'done': True}).status_code == 404
    assert c.put(url(org, 'applies'), headers=h(owner), json={'done': True}).status_code == 422
    assert c.put(url(org, 'dis'), headers=h(owner), json={'done': True, 'choice': 'yes'}).status_code == 422
    assert c.put(url(org, 'applies'), headers=h(owner), json={'done': True, 'choice': 'maybe'}).status_code == 422


def test_other_companies_cannot_read_or_tick():
    owner, _, _, org = company()
    stranger, _, _, _ = company()
    assert c.get(url(org), headers=h(stranger)).status_code == 403
    assert c.put(url(org, 'dis'), headers=h(stranger), json={'done': True}).status_code == 403
