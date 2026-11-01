"""Collaboration acceptance: isolation, retries, privacy, conflicts and migrations."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from test_api import c, h, user

from app import tasks
from app.database import Transaction, connection


@pytest.fixture
def team():
    owner, accountant, employee, outsider = [user(name) for name in
                                            ('Task owner', 'Task accountant', 'Task staff', 'Other owner')]
    org = c.post('/v1/organizations', json={'name': 'Synthetic task company'}, headers=h(owner)).json()['id']
    other = c.post('/v1/organizations', json={'name': 'Other synthetic company'}, headers=h(outsider)).json()['id']
    for actor, role in ((accountant, 'accountant'), (employee, 'employee')):
        invitation = c.post(f'/v1/organizations/{org}/members', headers=h(owner),
                            json={'user_id': actor, 'role': role}).json()['id']
        assert c.post(f'/v1/invitations/{invitation}/accept', headers=h(actor)).status_code == 200
    return {'owner': owner, 'accountant': accountant, 'employee': employee, 'outsider': outsider,
            'org': org, 'other': other, 'url': f'/v1/organizations/{org}/tasks'}


def keyed(actor, key=None):
    return {**h(actor), 'Idempotency-Key': key or str(uuid4())}


def create(team, **body):
    response = c.post(team['url'], headers=keyed(team['accountant']),
                      json={'title': 'Bổ sung chứng từ', **body})
    assert response.status_code == 201, response.text
    return response.json()


def move(team, task, status, actor='accountant', reason='Synthetic reason'):
    return c.patch(team['url'] + '/' + task['id'], headers=h(team[actor]),
                   json={'version': task['version'], 'status': status, 'reason': reason})


def test_accountant_client_round_trip_and_reopening(team):
    task = create(team)
    assert task['version'] == 1
    assert 'request_hash' not in task and 'idempotency_key' not in task
    waiting = move(team, task, 'WAITING_CLIENT').json()
    response = c.post(team['url'] + '/' + task['id'] + '/comments', headers=keyed(team['owner']),
                      json={'body': 'Đã bổ sung thông tin trên hóa đơn.'})
    assert response.status_code == 201
    review = move(team, waiting, 'IN_REVIEW', 'owner').json()
    assert move(team, review, 'DONE', 'owner').status_code == 403
    done = move(team, review, 'DONE').json()
    assert done['status'] == 'DONE' and done['version'] == 4
    assert move(team, done, 'REOPENED', reason='').status_code == 422
    reopened = move(team, done, 'REOPENED').json()
    assert reopened['version'] == 5
    history = c.get(team['url'] + '/' + task['id'] + '/events', headers=h(team['owner'])).json()['items']
    assert [row['to_status'] for row in reversed(history)] == [
        'OPEN', 'WAITING_CLIENT', 'IN_REVIEW', 'DONE', 'REOPENED']


@pytest.mark.parametrize('actor', ['employee', 'outsider'])
def test_all_task_surfaces_check_membership(team, actor):
    task = create(team)
    url = team['url'] + '/' + task['id']
    for path in (team['url'], team['url'] + '/summary', url, url + '/events', url + '/comments'):
        assert c.get(path, headers=h(team[actor])).status_code == 403
    assert c.post(team['url'], headers=keyed(team[actor]), json={'title': 'No'}).status_code == 403
    assert c.patch(url, headers=h(team[actor]), json={'version': 1, 'status': 'IN_PROGRESS'}).status_code == 403
    assert c.post(url + '/comments', headers=keyed(team[actor]), json={'body': 'No'}).status_code == 403


def test_authenticated_own_org_does_not_accept_other_org_task_or_document(team):
    task = create(team)
    other_url = f"/v1/organizations/{team['other']}/tasks"
    for suffix in ('', '/events', '/comments'):
        assert c.get(other_url + '/' + task['id'] + suffix, headers=h(team['outsider'])).status_code == 404
    assert c.patch(other_url + '/' + task['id'], headers=h(team['outsider']),
                   json={'version': 1, 'status': 'IN_PROGRESS'}).status_code == 404
    assert c.post(other_url + '/' + task['id'] + '/comments', headers=keyed(team['outsider']),
                  json={'body': 'No'}).status_code == 404
    doc = c.post(f"/v1/organizations/{team['other']}/documents", headers=h(team['outsider']),
                 files={'file': ('sample.pdf', b'%PDF-1.4\nSynthetic', 'application/pdf')}).json()['id']
    assert c.post(team['url'], headers=keyed(team['owner']),
                  json={'title': 'Wrong document', 'document_id': doc}).status_code == 404
    # Composite FK also prevents bypassing the application-level check.
    with pytest.raises(IntegrityError):
        with connection() as db:
            db.execute('UPDATE accounting_tasks SET document_id=? WHERE id=?', (doc, task['id']))


def test_revoked_membership_denies_previously_known_tasks(team):
    task = create(team)
    with connection() as db:
        db.execute('DELETE FROM memberships WHERE organization_id=? AND user_id=?',
                   (team['org'], team['accountant']))
    for suffix in ('', '/events', '/comments'):
        assert c.get(team['url'] + '/' + task['id'] + suffix,
                     headers=h(team['accountant'])).status_code == 403
    assert move(team, task, 'IN_PROGRESS').status_code == 403


def test_idempotent_create_conflict_and_scoped_key(team):
    key, body = str(uuid4()), {'title': 'One request'}
    first = c.post(team['url'], headers=keyed(team['accountant'], key), json=body)
    again = c.post(team['url'], headers=keyed(team['accountant'], key), json=body)
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()['id'] == again.json()['id']
    assert c.post(team['url'], headers=keyed(team['accountant'], key),
                  json={'title': 'Different request'}).status_code == 409
    assert c.post(team['url'], headers=keyed(team['owner'], key), json=body).status_code == 201
    with connection() as db:
        assert db.execute('SELECT COUNT(*) AS n FROM task_events WHERE task_id=?',
                          (first.json()['id'],)).fetchone()['n'] == 1


def test_internal_notes_filtered_before_pagination_and_never_return_keys(team):
    task = create(team)
    url = team['url'] + '/' + task['id'] + '/comments'
    public = c.post(url, headers=keyed(team['accountant']), json={'body': 'Visible'}).json()
    hidden = c.post(url, headers=keyed(team['accountant']),
                    json={'body': 'Internal note', 'visibility': 'accountant'}).json()
    assert 'request_hash' not in hidden and 'idempotency_key' not in hidden
    owner_page = c.get(url, params={'limit': 1}, headers=h(team['owner'])).json()
    assert owner_page['items'] == [public] and owner_page['next_cursor'] is None
    assert len(c.get(url, headers=h(team['accountant'])).json()['items']) == 2
    assert c.get(url, params={'cursor': hidden['id']}, headers=h(team['owner'])).status_code == 422
    assert c.post(url, headers=keyed(team['owner']),
                  json={'body': 'Forbidden', 'visibility': 'accountant'}).status_code == 403
    key = str(uuid4())
    a = c.post(url, headers=keyed(team['owner'], key), json={'body': 'Reply'})
    b = c.post(url, headers=keyed(team['owner'], key), json={'body': 'Reply'})
    assert a.json() == b.json() and b.status_code == 200
    assert c.post(url, headers=keyed(team['owner'], key), json={'body': 'Changed'}).status_code == 409


@pytest.mark.parametrize('body', [
    {'title': '   '}, {'title': 'x' * 181}, {'title': 'x', 'due_date': '2026-02-30'},
    {'title': 'x', 'organization_id': 'spoof'}, {'title': 'x', 'status': 'DONE'},
    {'title': 'x', 'priority': 'urgent'}, {'title': 'x', 'document_id': ''},
])
def test_invalid_create_has_no_side_effect(team, body):
    assert c.post(team['url'], headers=keyed(team['owner']), json=body).status_code == 422
    assert c.get(team['url'], headers=h(team['owner'])).json()['items'] == []


def test_missing_identity_and_key_and_blank_comment(team):
    assert c.get(team['url']).status_code == 401
    assert c.post(team['url'], headers=h(team['owner']), json={'title': 'No key'}).status_code == 422
    task = create(team)
    assert c.post(team['url'] + '/' + task['id'] + '/comments', headers=keyed(team['owner']),
                  json={'body': '  '}).status_code == 422
    assert move(team, task, 'DONE').status_code == 409
    assert move(team, task, 'WAITING_CLIENT', reason='  ').status_code == 422
    assert move(team, task, 'IN_PROGRESS').status_code == 200
    assert move(team, task, 'WAITING_CLIENT').status_code == 409


def test_cancellation_is_terminal(team):
    task = move(team, create(team), 'CANCELLED').json()
    assert task['available_transitions'] == []
    assert move(team, task, 'REOPENED').status_code == 409


def test_prague_due_dates_summary_and_cursor_scoping(team, monkeypatch):
    monkeypatch.setattr(tasks, 'today_prague', lambda: '2026-11-01')
    late = create(team, due_date='2026-10-31')
    current = create(team, due_date='2026-11-01')
    cancelled = move(team, create(team, due_date='2026-10-30'), 'CANCELLED').json()
    assert late['is_overdue'] and not current['is_overdue'] and not cancelled['is_overdue']
    summary = c.get(team['url'] + '/summary', headers=h(team['owner'])).json()
    assert summary['overdue'] == 1 and summary['by_status']['OPEN'] == 2
    assert summary['timezone'] == 'Europe/Prague'
    first = c.get(team['url'], params={'limit': 2}, headers=h(team['owner'])).json()
    second = c.get(team['url'], params={'limit': 2, 'cursor': first['next_cursor']},
                   headers=h(team['owner'])).json()
    assert len({x['id'] for x in first['items'] + second['items']}) == 3
    assert second['next_cursor'] is None
    assert [row['id'] for row in c.get(team['url'], params={'overdue': 'true'},
                                      headers=h(team['owner'])).json()['items']] == [late['id']]
    other = f"/v1/organizations/{team['other']}/tasks"
    assert c.get(other, params={'cursor': first['next_cursor']}, headers=h(team['outsider'])).status_code == 422


@pytest.mark.parametrize('operation', ['create', 'transition', 'comment'])
def test_concurrent_requests_commit_once(team, monkeypatch, operation):
    task = create(team)
    gate = Barrier(2)
    original = Transaction.execute
    prefix = {'create': 'INSERT INTO accounting_tasks', 'transition': 'UPDATE accounting_tasks SET status=',
              'comment': 'INSERT INTO task_comments'}[operation]

    def synchronize(self, statement, parameters=()):
        if statement.startswith(prefix):
            gate.wait(timeout=10)
        return original(self, statement, parameters)

    monkeypatch.setattr(Transaction, 'execute', synchronize)
    key = str(uuid4())

    def request(_):
        if operation == 'transition':
            return move(team, task, 'IN_PROGRESS')
        url = team['url'] + ('/' + task['id'] + '/comments' if operation == 'comment' else '')
        body = {'body': 'Concurrent reply'} if operation == 'comment' else {'title': 'Concurrent task'}
        return c.post(url, headers=keyed(team['accountant'], key), json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(request, (0, 1)))
    assert sorted(r.status_code for r in responses) == ([200, 409] if operation == 'transition' else [200, 201])
    if operation != 'transition':
        assert responses[0].json()['id'] == responses[1].json()['id']
    else:
        events = c.get(team['url'] + '/' + task['id'] + '/events', headers=h(team['owner'])).json()['items']
        assert len(events) == 2 and events[0]['version'] == 2


def test_event_failure_rolls_back_transition(team, monkeypatch):
    task = create(team)

    def fail(*args):
        raise RuntimeError('Simulated history failure')

    monkeypatch.setattr(tasks, 'record_event', fail)
    with pytest.raises(RuntimeError, match='history failure'):
        move(team, task, 'IN_PROGRESS')
    stored = c.get(team['url'] + '/' + task['id'], headers=h(team['owner'])).json()
    assert stored['version'] == 1 and stored['status'] == 'OPEN'
