"""CR-1 invoice data per document: roles, tenancy, versions, locking, VAT checks. Synthetic data only."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from test_api import c, h, user

from app import main
from app.database import Transaction

FIELDS = {
    'supplier_name': 'Synthetic Wholesale s.r.o., Praha', 'supplier_vat_id': 'CZ00000001',
    'document_number': 'SYN-204', 'subject': 'Potraviny a drogerie', 'issue_date': '2026-10-30',
    'currency': 'CZK', 'total': '3208.00',
    'lines': [{'rate': '12', 'base': '2000.00', 'tax': '240.00'},
              {'rate': '21', 'base': '800.00', 'tax': '168.00'}],
}


def company():
    owner, accountant, employee = user('Data owner'), user('Data accountant'), user('Data employee')
    org = c.post('/v1/organizations', json={'name': 'Invoice data'}, headers=h(owner)).json()['id']
    for member, role in ((accountant, 'accountant'), (employee, 'employee')):
        invite = c.post(f'/v1/organizations/{org}/members', json={'user_id': member, 'role': role}, headers=h(owner))
        assert c.post(f"/v1/invitations/{invite.json()['id']}/accept", headers=h(member)).status_code == 200
    upload = c.post(f'/v1/organizations/{org}/documents', headers=h(employee),
                    files={'file': ('receipt.pdf', b'%PDF-1.4\nSynthetic receipt', 'application/pdf')})
    assert upload.status_code == 201
    return owner, accountant, employee, org, upload.json()['id']


def url(org, did):
    return f'/v1/organizations/{org}/documents/{did}/extraction'


def put(org, did, who, version, fields=FIELDS, **extra):
    return c.put(url(org, did), headers=h(who), json={'version': version, 'fields': fields, **extra})


def test_owner_records_data_and_accountant_reads_checked_result():
    owner, accountant, _, org, did = company()
    assert c.get(url(org, did), headers=h(accountant)).status_code == 404
    saved = put(org, did, owner, 0)
    assert saved.status_code == 200
    body = saved.json()
    assert body['version'] == 1 and body['source'] == 'manual' and body['updated_by'] == owner
    assert body['check'] == {'kind': 'simplified', 'complete': True, 'findings': []}
    assert body['fields']['lines'][0] == {'rate': '12', 'base': '2000.00', 'tax': '240.00'}
    read = c.get(url(org, did), headers=h(accountant))
    assert read.status_code == 200 and read.json() == body
    audit = c.get(f'/v1/organizations/{org}/audit', headers=h(owner)).json()
    assert any(e['event'] == 'document.extraction_saved' and e['document_id'] == did for e in audit)


def test_findings_carry_legal_basis_and_are_stored():
    owner, accountant, _, org, did = company()
    fields = {**FIELDS, 'supplier_vat_id': '', 'total': '3308.00'}
    check = put(org, did, accountant, 0, fields).json()['check']
    assert check['complete'] is False
    codes = {f['code']: f for f in check['findings']}
    assert codes['supplier_vat_id_missing']['basis'] == '§ 29 odst. 1 písm. b) zákon č. 235/2004 Sb.'
    assert codes['total_mismatch']['detail'] == {'computed': '3208.00', 'stated': '3308.00'}
    assert c.get(url(org, did), headers=h(owner)).json()['check'] == check


def test_versions_are_required_and_revisions_are_append_only():
    owner, accountant, _, org, did = company()
    assert put(org, did, owner, 1).status_code == 409  # nothing to update yet
    assert put(org, did, owner, 0).status_code == 200
    assert put(org, did, owner, 0).status_code == 409  # stale
    corrected = put(org, did, accountant, 1, {**FIELDS, 'document_number': 'SYN-204A'})
    assert corrected.status_code == 200 and corrected.json()['version'] == 2
    with main.conn() as db:
        rows = db.execute('SELECT version, actor_id, fields FROM document_extractions WHERE document_id=? '
                          'ORDER BY version', (did,)).fetchall()
    assert [(r['version'], r['actor_id']) for r in rows] == [(1, owner), (2, accountant)]
    assert '"SYN-204"' in rows[0]['fields']  # first revision kept as written


def test_employee_and_outsiders_cannot_read_or_write():
    _, _, employee, org, did = company()
    stranger = user('Data stranger')
    for who in (employee, stranger):
        assert c.get(url(org, did), headers=h(who)).status_code == 403
        assert put(org, did, who, 0).status_code == 403


def test_document_of_another_company_is_not_found():
    owner_a, _, _, org_a, did_a = company()
    owner_b, _, _, org_b, _ = company()
    assert put(org_b, did_a, owner_b, 0).status_code == 404
    assert c.get(url(org_b, did_a), headers=h(owner_b)).status_code == 404
    assert put(org_a, did_a, owner_a, 0).status_code == 200


def test_money_must_be_strings_and_body_is_strict():
    owner, _, _, org, did = company()
    assert put(org, did, owner, 0, {**FIELDS, 'total': 3208.0}).status_code == 422
    assert put(org, did, owner, 0, {**FIELDS, 'lines': [{'rate': 21, 'base': '1.00', 'tax': '0.21'}]}).status_code == 422
    assert put(org, did, owner, 0, {**FIELDS, 'total': '32,08'}).status_code == 422
    assert put(org, did, owner, 0, {**FIELDS, 'deductible': True}).status_code == 422
    assert put(org, did, owner, 0, {**FIELDS, 'lines': [{'rate': '21'}] * 11}).status_code == 422
    assert put(org, did, owner, 0, source='ocr:any').status_code == 422
    assert c.get(url(org, did), headers=h(owner)).status_code == 404  # nothing was stored


def test_data_is_locked_after_a_decision_but_open_while_changes_are_requested():
    owner, accountant, _, org, did = company()
    assert put(org, did, owner, 0).status_code == 200
    review = f'/v1/organizations/{org}/documents/{did}/review'
    assert c.post(review, headers=h(accountant), json={'decision': 'request_changes'}).status_code == 200
    assert put(org, did, owner, 1).status_code == 200  # needs_changes stays editable
    other = company()
    assert c.post(f'/v1/organizations/{other[3]}/documents/{other[4]}/review', headers=h(other[1]),
                  json={'decision': 'approve'}).status_code == 200
    locked = put(other[3], other[4], other[0], 0)
    assert locked.status_code == 409 and 'locked' in locked.json()['detail']


def test_concurrent_saves_of_the_same_version_keep_one(monkeypatch):
    owner, accountant, _, org, did = company()
    gate = Barrier(2)
    original = Transaction.execute

    def synchronized(self, statement, parameters=()):
        if statement.startswith('UPDATE documents SET status=status'):
            gate.wait(timeout=10)
        return original(self, statement, parameters)

    monkeypatch.setattr(Transaction, 'execute', synchronized)

    def save(who):
        return put(org, did, who, 0, {**FIELDS, 'document_number': f'SYN-{who[:6]}'}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(save, (owner, accountant)))
    monkeypatch.setattr(Transaction, 'execute', original)
    assert statuses == [200, 409]
    with main.conn() as db:
        assert db.execute('SELECT COUNT(*) AS n FROM document_extractions WHERE document_id=?',
                          (did,)).fetchone()['n'] == 1
