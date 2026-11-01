"""Force review requests to reach the write together; verify one winner."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from app import main
from app.database import Transaction
from test_api import c, user, h


@pytest.mark.parametrize('decisions', [('approve','approve'), ('approve','reject')])
def test_concurrent_reviews_commit_one_decision(monkeypatch, decisions):
    owner=user('Review owner')
    org=c.post('/v1/organizations',json={'name':'Review race'},headers=h(owner)).json()['id']
    upload=c.post(f'/v1/organizations/{org}/documents',headers=h(owner),
                  files={'file':('synthetic.pdf',b'%PDF-1.4\nSynthetic','application/pdf')})
    assert upload.status_code==201
    did=upload.json()['id']
    gate=Barrier(2)
    original=Transaction.execute
    def synchronized_write(self, statement, parameters=()):
        if statement.startswith('UPDATE documents SET status='):
            gate.wait(timeout=10)
        return original(self, statement, parameters)
    monkeypatch.setattr(Transaction,'execute',synchronized_write)
    def review(decision):
        response=c.post(f'/v1/organizations/{org}/documents/{did}/review',
                        headers=h(owner),json={'decision':decision})
        return response.status_code, response.json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(review, decisions))
    assert sorted(status for status,_ in responses)==[200,409]
    winning=next(body['status'] for status,body in responses if status==200)
    with main.conn() as db:
        row=db.execute('SELECT status FROM documents WHERE id=?',(did,)).fetchone()
        events=db.execute("SELECT event FROM audit_events WHERE document_id=? AND event IN ('document.approved','document.rejected')",(did,)).fetchall()
    assert row['status']==winning
    assert [event['event'] for event in events]==['document.'+winning]
