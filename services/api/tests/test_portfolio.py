"""CR-6 accountant portfolio: counts per company, attention order, scope. Synthetic data only."""
from uuid import uuid4

from test_api import c, h, user
from test_archive import FIELDS, record, upload


def company(name, owner, accountant=None, employee=None):
    org = c.post('/v1/organizations', json={'name': name}, headers=h(owner)).json()['id']
    for member, role in ((accountant, 'accountant'), (employee, 'employee')):
        if member:
            invite = c.post(f'/v1/organizations/{org}/members', json={'user_id': member, 'role': role}, headers=h(owner))
            c.post(f"/v1/invitations/{invite.json()['id']}/accept", headers=h(member))
    return org


def task(org, who, due=None):
    body = {'title': 'Synthetic: doplnit doklad', 'description': '', 'priority': 'normal', 'due_date': due}
    return c.post(f'/v1/organizations/{org}/tasks', json=body, headers={**h(who), 'Idempotency-Key': str(uuid4())})


def portfolio(who):
    return c.get('/v1/portfolio', headers=h(who)).json()


def test_portfolio_counts_work_per_company_and_puts_urgent_first():
    accountant = user('Portfolio accountant')
    quiet_owner, busy_owner, late_owner = user('Quiet owner'), user('Busy owner'), user('Late owner')
    quiet = company('A Quiet Bistro', quiet_owner, accountant)
    busy = company('B Busy Potraviny', busy_owner, accountant)
    late = company('C Late Nails', late_owner, accountant)
    for n in range(3):
        upload(busy, busy_owner, f'%PDF-1.4\nBusy {n}'.encode())
    paid, unpaid = (upload(busy, busy_owner, f'%PDF-1.4\nApproved {n}'.encode()).json()['id'] for n in range(2))
    for did in (paid, unpaid):
        record(busy, busy_owner, did)
        c.post(f'/v1/organizations/{busy}/documents/{did}/review', headers=h(accountant), json={'decision': 'approve'})
    c.post(f'/v1/organizations/{busy}/cashbook', headers={**h(busy_owner), 'Idempotency-Key': str(uuid4())},
           json={'kind': 'expense', 'entry_date': '2026-10-30', 'amount': FIELDS['total'], 'method': 'bank',
                 'category': 'goods', 'document_id': paid})
    assert task(late, accountant, due='2020-01-01').status_code == 201
    assert task(late, accountant).status_code == 201
    body = portfolio(accountant)
    assert [i['name'] for i in body['items']] == ['C Late Nails', 'B Busy Potraviny', 'A Quiet Bistro']
    items = {i['organization_id']: i for i in body['items']}
    assert (items[late]['attention'], items[late]['open_tasks'], items[late]['overdue_tasks']) == ('high', 2, 1)
    assert (items[busy]['attention'], items[busy]['documents_to_review'], items[busy]['approved_without_payment']) == \
        ('medium', 3, 1)
    assert items[quiet]['attention'] == 'low' and items[quiet]['last_activity_at']
    assert body['timezone'] == 'Europe/Prague'


def test_task_work_counts_as_recent_activity():
    owner, accountant = user('Activity owner'), user('Activity accountant')
    org = company('Activity s.r.o.', owner, accountant)
    before = portfolio(accountant)['items'][0]['last_activity_at']
    made = task(org, accountant).json()
    reply = c.post(f"/v1/organizations/{org}/tasks/{made['id']}/comments", headers={**h(owner), 'Idempotency-Key': str(uuid4())},
                   json={'body': 'Synthetic reply', 'visibility': 'client'})
    assert reply.status_code == 201, reply.text
    after = portfolio(accountant)['items'][0]['last_activity_at']
    assert after > before


def test_portfolio_shows_only_the_users_finance_memberships():
    owner, accountant, employee, stranger = (user(n) for n in ('Scope owner', 'Scope acc', 'Scope emp', 'Scope x'))
    org = company('Scoped s.r.o.', owner, accountant, employee)
    upload(org, owner, b'%PDF-1.4\nScoped')
    assert [i['organization_id'] for i in portfolio(owner)['items']] == [org]
    assert [i['role'] for i in portfolio(accountant)['items']] == ['accountant']
    assert portfolio(employee)['items'] == [] and portfolio(stranger)['items'] == []
    assert c.get('/v1/portfolio').status_code == 401
