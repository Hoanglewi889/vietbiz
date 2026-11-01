import os
from pathlib import Path
from fastapi.testclient import TestClient
# Test data path isolated before main import.
import tempfile
from app.main import app
c=TestClient(app)
def user(name):
    r=c.post('/dev/users',params={'display_name':name});assert r.status_code==201;return r.json()['id']
def h(u):return {'X-User':u}
def test_tenant_isolation_and_review():
    owner=user('Owner');stranger=user('Stranger');accountant=user('Accountant')
    r=c.post('/v1/organizations',json={'name':'Potraviny Praha','ico':'12345678'},headers=h(owner));assert r.status_code==201
    org=r.json()['id']
    payload={'file':('receipt.pdf',b'%PDF-1.4\nexample synthetic', 'application/pdf')}
    assert c.post(f'/v1/organizations/{org}/documents',files=payload,headers=h(stranger)).status_code==403
    r=c.post(f'/v1/organizations/{org}/documents',files=payload,headers=h(owner));assert r.status_code==201
    did=r.json()['id']
    assert c.get(f'/v1/organizations/{org}/documents',headers=h(stranger)).status_code==403
    assert c.get(f'/v1/organizations/{org}/documents/{did}/original',headers=h(stranger)).status_code==403
    assert c.post(f'/v1/organizations/{org}/documents/{did}/review',json={'decision':'approve'},headers=h(stranger)).status_code==403
    invite=c.post(f'/v1/organizations/{org}/members',json={'user_id':accountant,'role':'accountant'},headers=h(owner))
    assert invite.status_code==201
    assert c.post(f"/v1/invitations/{invite.json()['id']}/accept",headers=h(accountant)).status_code==200
    assert c.post(f'/v1/organizations/{org}/documents/{did}/review',json={'decision':'approve'},headers=h(accountant)).json()['status']=='approved'
    assert c.post(f'/v1/organizations/{org}/documents/{did}/review',json={'decision':'approve'},headers=h(accountant)).status_code==409
    assert len(c.get(f'/v1/organizations/{org}/audit',headers=h(owner)).json())>=3

def test_file_validation():
    owner=user('Another Owner');org=c.post('/v1/organizations',json={'name':'Nail'},headers=h(owner)).json()['id']
    r=c.post(f'/v1/organizations/{org}/documents',files={'file':('wrong.pdf',b'not pdf','application/pdf')},headers=h(owner));assert r.status_code==415
    r=c.post(f'/v1/organizations/{org}/documents',files={'file':('script.html',b'<html>bad</html>','text/html')},headers=h(owner));assert r.status_code==415
