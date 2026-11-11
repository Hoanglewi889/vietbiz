"""VietBiz local prototype with opt-in demo identity and OIDC JWT verification."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from typing import Literal
import os
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Depends
from fastapi.responses import Response
from cryptography.exceptions import InvalidTag
from starlette.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

# Hard safety gate: demo X-User identity is spoofable and must never ship.
DEPLOYMENT_ENV = os.getenv('VIETBIZ_ENV', 'development').strip().lower()
if DEPLOYMENT_ENV not in {'development', 'test'}:
    raise RuntimeError('Unsafe authentication: VietBiz demo API cannot run outside development/test. Implement OIDC before deployment.')

AUTH_MODE = os.getenv('VIETBIZ_AUTH_MODE', 'oidc').strip().lower()
if AUTH_MODE not in {'demo', 'oidc'}:
    raise RuntimeError('Unknown authentication mode')
from .auth import configured_verifier, login_settings
VERIFIER = configured_verifier() if AUTH_MODE == 'oidc' else None

ROOT = Path(os.getenv('VIETBIZ_DATA_DIR', './.vietbiz-data')).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
FILES = ROOT / 'originals'
FILES.mkdir(exist_ok=True)
DB = ROOT / 'vietbiz.sqlite3'
MAX_BYTES = 10 * 1024 * 1024
MIMES = {'application/pdf':'.pdf','image/jpeg':'.jpg','image/png':'.png'}
app = FastAPI(title='VietBiz API — Sprint 10',version='0.10.0',description='LOCAL ONLY. OIDC JWT verification by default; explicit demo mode available.')
# Hardening (report 10.11.2026, gaps 3 and 4). The last middleware added is the outermost:
# rate limits innermost, then CORS (Codex review, PR #21: so an allowed origin can read a 429),
# then security headers outermost, so every answer, a 429 included, carries them.
from .web_security import Limits, RateLimit, SecurityHeaders, attachment_disposition
LIMITS = Limits.from_env()
app.add_middleware(RateLimit, limits=LIMITS)
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:3000','http://127.0.0.1:3000'],allow_methods=['*'],allow_headers=['*'])
app.add_middleware(SecurityHeaders)
from .crypto import data_key, document_context, seal, unseal
data_key()  # fail at start-up, not on the first upload, when the key is missing or malformed
from .database import connection as conn, require_schema
require_schema()

def current_user(x_user: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    if AUTH_MODE == 'oidc':
        uid = VERIFIER.verify(authorization)
        with conn() as c:
            c.execute('INSERT INTO users VALUES(?,?) ON CONFLICT(id) DO NOTHING', (uid, 'OIDC user'))
        return uid
    if not x_user: raise HTTPException(401,'DEMO: supply X-User header')
    with conn() as c:
        row=c.execute('SELECT * FROM users WHERE id=?',(x_user,)).fetchone()
    if not row: raise HTTPException(401,'Unknown demo user')
    return x_user


def authorize(c,uid,org,roles=('owner','employee','accountant')):
    r=c.execute('SELECT role FROM memberships WHERE organization_id=? AND user_id=?',(org,uid)).fetchone()
    if not r or r['role'] not in roles: raise HTTPException(403,'No access to this organization')
    return r['role']

def event(c,org,uid,name,did=None):
    c.execute('INSERT INTO audit_events VALUES(?,?,?,?,?,?)',(str(uuid4()),org,uid,name,did,datetime.now(timezone.utc).isoformat()))

class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1,max_length=150)
    ico: str | None = Field(default=None,pattern=r'^\d{8}$')
class MembershipCreate(BaseModel):
    user_id:str
    role:Literal['employee','accountant']
class ReviewRequest(BaseModel):
    decision:Literal['approve','reject','request_changes']

@app.get('/auth/config')
def auth_config():
    """Public login settings for the workspace (no secrets: the web client is public + PKCE)."""
    return login_settings(AUTH_MODE)

@app.get('/health')
def health():return {'status':'ok','mode':DEPLOYMENT_ENV,'auth_mode':AUTH_MODE}
@app.get('/v1/me')
def me(uid:str=Depends(current_user)):
    return {'id':uid}

@app.post('/dev/users',status_code=201)
def dev_user(display_name:str):
    if AUTH_MODE != 'demo': raise HTTPException(404, 'Not found')
    uid=str(uuid4())
    with conn() as c:c.execute('INSERT INTO users VALUES(?,?)',(uid,display_name[:120]))
    return {'id':uid,'display_name':display_name[:120]}
@app.post('/v1/organizations',status_code=201)
def create_org(payload:OrganizationCreate,uid:str=Depends(current_user)):
    oid=str(uuid4())
    with conn() as c:
        c.execute('INSERT INTO organizations VALUES(?,?,?)',(oid,payload.name,payload.ico))
        c.execute('INSERT INTO memberships VALUES(?,?,?)',(uid,oid,'owner'))
        event(c,oid,uid,'organization.created')
    return {'id':oid,'name':payload.name,'ico':payload.ico}
@app.get('/v1/organizations')
def get_orgs(uid:str=Depends(current_user)):
    with conn() as c:
        rows=c.execute('SELECT o.*,m.role FROM organizations o JOIN memberships m ON o.id=m.organization_id WHERE m.user_id=?',(uid,)).fetchall()
    return [dict(x) for x in rows]
@app.post('/v1/organizations/{org_id}/members',status_code=201)
def invite_member(org_id:str,body:MembershipCreate,uid:str=Depends(current_user)):
    if uid==body.user_id: raise HTTPException(400,'Owner cannot invite themselves')
    invitation_id=str(uuid4())
    now=datetime.now(timezone.utc)
    expires=(now+timedelta(days=7)).isoformat()
    with conn() as c:
        authorize(c,uid,org_id,('owner',))
        if not c.execute('SELECT 1 FROM users WHERE id=?',(body.user_id,)).fetchone():raise HTTPException(404,'User not found')
        if c.execute('SELECT 1 FROM memberships WHERE organization_id=? AND user_id=?',(org_id,body.user_id)).fetchone():
            raise HTTPException(409,'Member already belongs to organization')
        c.execute("UPDATE invitations SET revoked_at=? WHERE organization_id=? AND invitee_id=? AND status='pending' AND revoked_at IS NULL AND expires_at<=?",
                  (now.isoformat(),org_id,body.user_id,now.isoformat()))
        try:
            c.execute('INSERT INTO invitations (id,organization_id,invitee_id,role,inviter_id,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)',
                      (invitation_id,org_id,body.user_id,body.role,uid,'pending',now.isoformat(),expires))
        except IntegrityError:
            raise HTTPException(409,'Invitation already pending') from None
        event(c,org_id,uid,'membership.invited')
    return {'id':invitation_id,'organization_id':org_id,'status':'pending','expires_at':expires}

@app.get('/v1/invitations')
def my_invitations(uid:str=Depends(current_user)):
    with conn() as c:
        rows=c.execute("SELECT id,organization_id,role,created_at,expires_at FROM invitations WHERE invitee_id=? AND status='pending' AND revoked_at IS NULL AND expires_at>? ORDER BY created_at DESC",
                       (uid,datetime.now(timezone.utc).isoformat())).fetchall()
    return [dict(row) for row in rows]

@app.post('/v1/organizations/{org_id}/invitations/{invitation_id}/revoke')
def revoke_invitation(org_id:str,invitation_id:str,uid:str=Depends(current_user)):
    with conn() as c:
        authorize(c,uid,org_id,('owner',))
        row=c.execute('SELECT status,revoked_at FROM invitations WHERE id=? AND organization_id=?',(invitation_id,org_id)).fetchone()
        if not row: raise HTTPException(404,'Invitation not found')
        if row['revoked_at']: return {'id':invitation_id,'status':'revoked'}
        changed=c.execute("UPDATE invitations SET revoked_at=? WHERE id=? AND organization_id=? AND status='pending' AND revoked_at IS NULL",
                          (datetime.now(timezone.utc).isoformat(),invitation_id,org_id))
        if changed.rowcount!=1: raise HTTPException(409,'Invitation already processed')
        event(c,org_id,uid,'membership.invitation_revoked')
    return {'id':invitation_id,'status':'revoked'}

@app.post('/v1/invitations/{invitation_id}/accept')
def accept_invitation(invitation_id:str,uid:str=Depends(current_user)):
    with conn() as c:
        row=c.execute('SELECT * FROM invitations WHERE id=?',(invitation_id,)).fetchone()
        if not row:raise HTTPException(404,'Invitation not found')
        if row['invitee_id']!=uid:raise HTTPException(403,'Only invitee may accept')
        # Conditional UPDATE claims the invitation once, within the membership transaction.
        claimed=c.execute("UPDATE invitations SET status='accepted' WHERE id=? AND invitee_id=? AND status='pending' AND revoked_at IS NULL AND expires_at>?",
                          (invitation_id,uid,datetime.now(timezone.utc).isoformat()))
        if claimed.rowcount!=1: raise HTTPException(409,'Invitation expired, revoked or already processed')
        # An invitation is no longer valid if its issuer no longer owns the organization.
        authorize(c,row['inviter_id'],row['organization_id'],('owner',))
        inserted=c.execute('INSERT INTO memberships VALUES(?,?,?) ON CONFLICT(user_id,organization_id) DO NOTHING',
                           (uid,row['organization_id'],row['role']))
        if inserted.rowcount!=1: raise HTTPException(409,'Already a member')
        event(c,row['organization_id'],uid,'membership.accepted')
    return {'id':invitation_id,'status':'accepted'}

@app.post('/v1/organizations/{org_id}/documents',status_code=201)
async def upload_document(org_id:str,file:UploadFile=File(...),uid:str=Depends(current_user)):
    with conn() as c:authorize(c,uid,org_id,('owner','employee'))
    mime=file.content_type or ''
    if mime not in MIMES:raise HTTPException(415,'Only PDF, JPEG and PNG')
    content=await file.read(MAX_BYTES+1)
    if len(content)>MAX_BYTES:raise HTTPException(413,'File larger than 10 MB')
    if not content:raise HTTPException(422,'Empty file')
    magic=(mime=='application/pdf' and content.startswith(b'%PDF-')) or (mime=='image/jpeg' and content.startswith(b'\xff\xd8\xff')) or (mime=='image/png' and content.startswith(b'\x89PNG\r\n\x1a\n'))
    if not magic:raise HTTPException(415,'MIME and file signature differ')
    # PDF parsing is CPU-bound; keep it off the event loop.
    isdoc_fields=await run_in_threadpool(read_isdoc,content) if mime=='application/pdf' else None
    did=str(uuid4()); org_dir=FILES / org_id;org_dir.mkdir(exist_ok=True)
    # Gap 2: the original is sealed (AES-256-GCM, bound to this company and document) before it
    # touches the disk; the digest and size describe the plain file.
    target=org_dir / (did+MIMES[mime]); target.write_bytes(seal(content,document_context(org_id,did)))
    digest=sha256(content).hexdigest()
    try:
      with conn() as c:
        # Lock the company row so two uploads of the same file cannot both pass the check.
        c.execute('UPDATE organizations SET id=id WHERE id=?',(org_id,))
        existing=c.execute('SELECT id FROM documents WHERE organization_id=? AND sha256=?',(org_id,digest)).fetchone()
        if existing:raise HTTPException(409,{'code':'duplicate_file','document_id':existing['id']})
        c.execute('INSERT INTO documents(id,organization_id,uploader_id,filename,mime,storage_path,sha256,size_bytes,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(did,org_id,uid,(file.filename or 'upload')[:200],mime,str(target),digest,len(content),'needs_review',datetime.now(timezone.utc).isoformat()))
        event(c,org_id,uid,'document.uploaded',did)
        goods=isdoc_fields.pop('goods_lines',[]) if isdoc_fields else []
        if record_isdoc(c,org_id,uid,did,isdoc_fields):
          event(c,org_id,uid,'document.extraction_imported',did)
          if import_goods_lines(c,org_id,uid,did,goods):event(c,org_id,uid,'document.lines_imported',did)
    except Exception:
      target.unlink(missing_ok=True)
      raise
    return {'id':did,'organization_id':org_id,'status':'needs_review','sha256':sha256(content).hexdigest(),'size_bytes':len(content)}
@app.get('/v1/organizations/{org_id}/documents')
def documents(org_id:str,uid:str=Depends(current_user)):
    with conn() as c:
        authorize(c,uid,org_id)
        rows=c.execute('SELECT id,organization_id,filename,mime,sha256,size_bytes,status,created_at FROM documents WHERE organization_id=? ORDER BY created_at DESC',(org_id,)).fetchall()
    return [dict(x) for x in rows]
@app.get('/v1/organizations/{org_id}/documents/{doc_id}/original')
def original(org_id:str,doc_id:str,uid:str=Depends(current_user)):
    with conn() as c:
        authorize(c,uid,org_id)
        d=c.execute('SELECT * FROM documents WHERE id=? AND organization_id=?',(doc_id,org_id)).fetchone()
        if not d:raise HTTPException(404,'Document not found')
        root=FILES.resolve()
        org_root=(root / org_id).resolve()
        path=Path(d['storage_path']).resolve()
        if org_root==root or not org_root.is_relative_to(root) or not path.is_relative_to(org_root) or not path.is_file():
            raise HTTPException(404,'Original file missing')
        try:
            content=unseal(path.read_bytes(),document_context(org_id,doc_id))
        except InvalidTag:
            raise HTTPException(500,'Original cannot be decrypted') from None
        # This records authorized access, not proof that the client received all bytes.
        event(c,org_id,uid,'document.download_requested',doc_id)
    return Response(content,media_type=d['mime'],headers={'Content-Disposition':attachment_disposition(d['filename'],'document')})
@app.post('/v1/organizations/{org_id}/documents/{doc_id}/review')
def review(org_id:str,doc_id:str,body:ReviewRequest,uid:str=Depends(current_user)):
    with conn() as c:
        authorize(c,uid,org_id,('accountant','owner'))
        new={'approve':'approved','reject':'rejected','request_changes':'needs_changes'}[body.decision]
        # Claim once, in the same transaction as the audit event.
        claimed=c.execute("UPDATE documents SET status=? WHERE id=? AND organization_id=? AND status='needs_review'",
                          (new,doc_id,org_id))
        if claimed.rowcount!=1:
            if not c.execute('SELECT 1 FROM documents WHERE id=? AND organization_id=?',(doc_id,org_id)).fetchone():
                raise HTTPException(404,'Document not found')
            raise HTTPException(409,'Document already processed')
        event(c,org_id,uid,'document.'+new,doc_id)
    return {'id':doc_id,'status':new}
@app.get('/v1/organizations/{org_id}/audit')
def audit(org_id:str,uid:str=Depends(current_user)):
    with conn() as c:
        authorize(c,uid,org_id,('owner','accountant'))
        rows=c.execute('SELECT event,actor_id,document_id,created_at FROM audit_events WHERE organization_id=? ORDER BY created_at DESC LIMIT 100',(org_id,)).fetchall()
    return [dict(x) for x in rows]

# News read-only public API. Editorial tools are deliberately CLI-only while demo auth is unsafe.
from .news import router as news_router
app.include_router(news_router)

from .tasks import build_router
app.include_router(build_router(current_user, authorize))

from .extractions import build_router as build_extraction_router, record_isdoc
from .isdoc import from_pdf as read_isdoc
from .archive import build_router as build_archive_router
app.include_router(build_archive_router(current_user, authorize, event))
from .cashbook import build_router as build_cashbook_router
app.include_router(build_cashbook_router(current_user, authorize, event))
from .invoicing import build_router as build_invoicing_router
app.include_router(build_invoicing_router(current_user, authorize, event))
from .portfolio import build_router as build_portfolio_router
from .goods import build_router as build_goods_router, import_goods_lines
app.include_router(build_goods_router(current_user, authorize, event))
app.include_router(build_portfolio_router(current_user))
from .bank import build_router as build_bank_router
from .staff import build_router as build_staff_router
from .cash_control import build_router as build_cash_control_router
app.include_router(build_staff_router(current_user, authorize, event))
app.include_router(build_cash_control_router(current_user, authorize, event))
app.include_router(build_bank_router(current_user, authorize, event))
from .vat_threshold import build_router as build_threshold_router
app.include_router(build_threshold_router(current_user, authorize))
from .filing_calendar import build_router as build_calendar_router
app.include_router(build_calendar_router(current_user, authorize, event))
app.include_router(build_extraction_router(current_user, authorize, event))

# Serve the local demo from the API origin; API authorization is unchanged.
from fastapi.staticfiles import StaticFiles
web_root = Path(__file__).resolve().parents[3] / 'apps' / 'accountant-web'
if web_root.is_dir():
    app.mount('/workspace', StaticFiles(directory=web_root, html=True), name='workspace')
