from concurrent.futures import ThreadPoolExecutor
from test_api import c, user, h
from app.main import conn


def setup_invite():
    owner, invitee, outsider = user('Owner'), user('Invitee'), user('Outsider')
    org=c.post('/v1/organizations',json={'name':'Invitation lifecycle'},headers=h(owner)).json()['id']
    invite=c.post(f'/v1/organizations/{org}/members',json={'user_id':invitee,'role':'accountant'},headers=h(owner))
    assert invite.status_code==201
    return owner,invitee,outsider,org,invite.json()['id']


def test_revoke_is_scoped_and_removes_access_to_accept():
    owner,invitee,outsider,org,iid=setup_invite()
    url=f'/v1/organizations/{org}/invitations/{iid}/revoke'
    assert c.post(url,headers=h(outsider)).status_code==403
    assert c.post(url,headers=h(invitee)).status_code==403
    assert c.post(url,headers=h(owner)).status_code==200
    assert c.post(url,headers=h(owner)).status_code==200
    assert c.post(f'/v1/invitations/{iid}/accept',headers=h(invitee)).status_code==409
    assert c.get('/v1/organizations',headers=h(invitee)).json()==[]
    assert c.get('/v1/invitations',headers=h(invitee)).json()==[]
    assert c.post(f'/v1/organizations/{org}/members',json={'user_id':invitee,'role':'employee'},headers=h(owner)).status_code==201


def test_expiry_and_private_inbox():
    owner,invitee,outsider,org,iid=setup_invite()
    assert [x['id'] for x in c.get('/v1/invitations',headers=h(invitee)).json()]==[iid]
    assert c.get('/v1/invitations',headers=h(outsider)).json()==[]
    with conn() as db: db.execute('UPDATE invitations SET expires_at=? WHERE id=?',('2000-01-01T00:00:00+00:00',iid))
    assert c.post(f'/v1/invitations/{iid}/accept',headers=h(invitee)).status_code==409
    assert c.get('/v1/invitations',headers=h(invitee)).json()==[]
    assert c.post(f'/v1/organizations/{org}/members',json={'user_id':invitee,'role':'accountant'},headers=h(owner)).status_code==201


def test_concurrent_accept_grants_exactly_one_membership():
    owner,invitee,outsider,org,iid=setup_invite()
    def accept(_): return c.post(f'/v1/invitations/{iid}/accept',headers=h(invitee)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(accept,range(2)))
    assert sorted(results)==[200,409]
    with conn() as db:
        assert len(db.execute('SELECT * FROM memberships WHERE organization_id=? AND user_id=?',(org,invitee)).fetchall())==1
        assert len(db.execute("SELECT * FROM audit_events WHERE organization_id=? AND event='membership.accepted'",(org,)).fetchall())==1
    assert c.post(f'/v1/organizations/{org}/invitations/{iid}/revoke',headers=h(owner)).status_code==409


def test_duplicate_invite_and_removed_owner():
    owner,invitee,outsider,org,iid=setup_invite()
    assert c.post(f'/v1/organizations/{org}/members',json={'user_id':invitee,'role':'employee'},headers=h(owner)).status_code==409
    with conn() as db: db.execute('DELETE FROM memberships WHERE user_id=? AND organization_id=?',(owner,org))
    assert c.post(f'/v1/invitations/{iid}/accept',headers=h(invitee)).status_code==403
    with conn() as db:
        assert db.execute('SELECT status FROM invitations WHERE id=?',(iid,)).fetchone()['status']=='pending'
        assert db.execute('SELECT * FROM memberships WHERE user_id=? AND organization_id=?',(invitee,org)).fetchone() is None


def test_accept_and_revoke_race_has_consistent_outcome():
    owner,invitee,outsider,org,iid=setup_invite()
    def action(kind):
        if kind=='accept': return c.post(f'/v1/invitations/{iid}/accept',headers=h(invitee)).status_code
        return c.post(f'/v1/organizations/{org}/invitations/{iid}/revoke',headers=h(owner)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(action,['accept','revoke']))
    assert sorted(results)==[200,409]
    with conn() as db:
        invite=db.execute('SELECT * FROM invitations WHERE id=?',(iid,)).fetchone()
        member=db.execute('SELECT * FROM memberships WHERE user_id=? AND organization_id=?',(invitee,org)).fetchone()
    if results[0]==200:
        assert member and invite['status']=='accepted' and invite['revoked_at'] is None
    else:
        assert member is None and invite['revoked_at'] is not None
