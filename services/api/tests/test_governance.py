from test_api import c, user, h
from app import main
import pytest

def test_invitation_requires_invitee_and_prevents_overwrite():
    owner=user('InviteOwner'); accountant=user('Invitee'); outsider=user('Outsider')
    org=c.post('/v1/organizations',json={'name':'Invite test'},headers=h(owner)).json()['id']
    invite=c.post(f'/v1/organizations/{org}/members',json={'user_id':accountant,'role':'accountant'},headers=h(owner))
    assert invite.status_code==201
    iid=invite.json()['id']
    assert c.get('/v1/organizations',headers=h(accountant)).json()==[]
    assert c.post(f'/v1/invitations/{iid}/accept',headers=h(outsider)).status_code==403
    assert c.post(f'/v1/invitations/{iid}/accept',headers=h(accountant)).status_code==200
    assert c.post(f'/v1/invitations/{iid}/accept',headers=h(accountant)).status_code==409
    assert c.post(f'/v1/organizations/{org}/members',json={'user_id':accountant,'role':'employee'},headers=h(owner)).status_code==409

def test_upload_cleans_file_on_database_failure(monkeypatch):
    owner=user('CleanupOwner')
    org=c.post('/v1/organizations',json={'name':'Cleanup test'},headers=h(owner)).json()['id']
    old=main.event
    def fail(*args,**kwargs):
        if args[3]=='document.uploaded': raise RuntimeError('simulated database failure')
        return old(*args,**kwargs)
    monkeypatch.setattr(main,'event',fail)
    before=set((main.FILES / org).glob('*')) if (main.FILES / org).exists() else set()
    with pytest.raises(RuntimeError):
        c.post(f'/v1/organizations/{org}/documents',files={'file':('example.pdf',b'%PDF-1.4\ntest','application/pdf')},headers=h(owner))
    after=set((main.FILES / org).glob('*'))
    assert after==before
