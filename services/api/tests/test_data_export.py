"""Company data export (GDPR art. 20, hand-over). Synthetic data only."""
import io
import json
import zipfile

from test_api import c, h
from test_archive import company, stocked
from test_bank import gpc_075
from test_invoicing import payer_company, url
from test_statements import header, send, statement


def export(org, who):
    return c.get(f'/v1/organizations/{org}/export', headers=h(who))


def unzip(response):
    return zipfile.ZipFile(io.BytesIO(response.content))


def test_the_owner_gets_every_table_and_the_decrypted_originals():
    owner, accountant, employee, org, d = stocked()
    other_owner, _, _, other = company()
    foreign = c.post(f'/v1/organizations/{other}/documents', headers=h(other_owner),
                     files={'file': ('x.pdf', b'%PDF-1.4\nForeign', 'application/pdf')}).json()['id']
    task = c.post(f'/v1/organizations/{org}/tasks', headers={**h(accountant), 'Idempotency-Key': 'export-task-1'},
                  json={'title': 'Synthetic export task', 'description': '', 'priority': 'normal',
                        'due_date': None, 'document_id': None}).json()['id']
    for i, (who, visibility) in enumerate(((owner, 'client'), (accountant, 'accountant'))):
        assert c.post(f'/v1/organizations/{org}/tasks/{task}/comments',
                      headers={**h(who), 'Idempotency-Key': f'export-comment-{i}'},
                      json={'body': f'synthetic {visibility} note', 'visibility': visibility}).status_code == 201
    r = export(org, owner)
    assert r.status_code == 200 and r.headers['content-type'] == 'application/zip'
    assert r.headers['content-disposition'].startswith('attachment; filename="vietbiz-export-')
    z = unzip(r)
    names = z.namelist()
    assert 'README.txt' in names and 'data/documents.json' in names and 'data/audit_events.json' in names
    docs = json.loads(z.read('data/documents.json'))
    assert {x['id'] for x in docs} == set(d.values()) and foreign not in json.dumps(docs)
    assert all('storage_path' not in x for x in docs)
    originals = [n for n in names if n.startswith('originals/documents/')]
    assert len(originals) == 4
    makro = next(n for n in originals if n.split('/')[-1].startswith(d['makro']))
    assert z.read(makro) == b'%PDF-1.4\nMakro'
    comments = json.loads(z.read('data/task_comments.json'))
    assert [x['body'] for x in comments] == ['synthetic client note']
    assert all('idempotency_key' not in x and 'request_hash' not in x for x in json.loads(z.read('data/accounting_tasks.json')))
    members = json.loads(z.read('data/memberships.json'))
    assert {m['role'] for m in members} == {'owner', 'accountant', 'employee'}
    events = [e['event'] for e in c.get(f'/v1/organizations/{org}/audit', headers=h(owner)).json()]
    assert 'organization.exported' in events


def test_statements_are_exported_decrypted():
    owner, accountant, employee, org = payer_company()
    body = statement(header('300926', 100000, 150000, 10, '311026'), gpc_075(50000, '2', ref='1', day='151026'))
    import_id = send(org, owner, body).json()['import_id']
    z = unzip(export(org, owner))
    files = [n for n in z.namelist() if n.startswith(f'originals/statements/{import_id}-')]
    assert len(files) == 1 and z.read(files[0]) == body
    assert len(json.loads(z.read('data/bank_transactions.json'))) == 1
    assert c.get(url(org, '/export'), headers=h(accountant)).status_code == 403


def test_only_the_owner_may_export():
    owner, accountant, employee, org, _ = stocked()
    assert export(org, accountant).status_code == 403
    assert export(org, employee).status_code == 403
    other_owner, _, _, _ = company()
    assert export(org, other_owner).status_code == 403
