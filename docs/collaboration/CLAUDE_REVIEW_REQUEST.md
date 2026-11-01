Bạn đang phối hợp với Codex cho dự án VietBiz của người dùng. Codex gửi đúng mã nguồn hiện có bên dưới để bạn review độc lập. Bạn không có quyền truy cập repo trực tiếp trong phiên web này; đừng nhận là đã chạy test hay sửa file.

Bối cảnh: VietBiz là prototype VI/CS cho SME ở Séc, FastAPI + SQLAlchemy, Alembic, SQLite local/PostgreSQL planned. Bản code Sprint07 có 44 tests passed SQLite theo lượt trước; PostgreSQL/live OIDC chưa chạy, production gate phải giữ. Sprint08 chỉ có nghiên cứu, chưa có cashbook, OCR, connector POHODA/MoneyS3 thật.

Nhiệm vụ cụ thể của bạn: review quyền truy cập và tính nguyên tử trong document upload/review/download và invitations. Chọn tối đa 3 lỗi thực sự có bằng chứng ở code, ghi đường dẫn/hàm và mức độ. Đề xuất unified diff nhỏ cho lỗi quan trọng có thể sửa ngay, kèm mã pytest hồi quy (đặc biệt đồng thời approve/reject hoặc hai review requests). Không thay đổi ngôn ngữ UI, không mở production, không gửi email, không dùng dịch vụ trả phí mới. Nếu chỉ là giả định rủi ro, ghi rõ. Giữ câu trả lời vừa đủ để Codex áp dụng patch và xác minh.


FILE services/api/app/main.py
```python
"""VietBiz local prototype with opt-in demo identity and OIDC JWT verification."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from typing import Literal
import os
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Depends
from fastapi.responses import FileResponse
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
from .auth import configured_verifier
VERIFIER = configured_verifier() if AUTH_MODE == 'oidc' else None

ROOT = Path(os.getenv('VIETBIZ_DATA_DIR', './.vietbiz-data')).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
FILES = ROOT / 'originals'
FILES.mkdir(exist_ok=True)
DB = ROOT / 'vietbiz.sqlite3'
MAX_BYTES = 10 * 1024 * 1024
MIMES = {'application/pdf':'.pdf','image/jpeg':'.jpg','image/png':'.png'}
app = FastAPI(title='VietBiz API — Sprint 01',version='0.1.0',description='LOCAL ONLY. OIDC JWT verification by default; explicit demo mode available.')
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:3000','http://127.0.0.1:3000'],allow_methods=['*'],allow_headers=['*'])
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
    did=str(uuid4()); org_dir=FILES / org_id;org_dir.mkdir(exist_ok=True)
    target=org_dir / (did+MIMES[mime]); target.write_bytes(content)
    try:
      with conn() as c:
        c.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?)',(did,org_id,uid,(file.filename or 'upload')[:200],mime,str(target),sha256(content).hexdigest(),len(content),'needs_review',datetime.now(timezone.utc).isoformat()))
        event(c,org_id,uid,'document.uploaded',did)
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
        event(c,org_id,uid,'document.downloaded',doc_id)
    return FileResponse(d['storage_path'],media_type=d['mime'],filename=d['filename'])
@app.post('/v1/organizations/{org_id}/documents/{doc_id}/review')
def review(org_id:str,doc_id:str,body:ReviewRequest,uid:str=Depends(current_user)):
    with conn() as c:
        authorize(c,uid,org_id,('accountant','owner'))
        d=c.execute('SELECT status FROM documents WHERE id=? AND organization_id=?',(doc_id,org_id)).fetchone()
        if not d:raise HTTPException(404,'Document not found')
        if d['status']!='needs_review':raise HTTPException(409,'Document already processed')
        new={'approve':'approved','reject':'rejected','request_changes':'needs_changes'}[body.decision]
        c.execute('UPDATE documents SET status=? WHERE id=?',(new,doc_id))
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

```

FILE services/api/app/database.py
```python
"""Shared SQLAlchemy transactions; schema changes belong to Alembic only."""
import os
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url

SCHEMA_REVISION = '0002_invitations'


def database_url():
    value = os.getenv('VIETBIZ_DATABASE_URL')
    if value:
        url = make_url(value)
        if url.drivername not in {'postgresql+psycopg', 'sqlite'}:
            raise RuntimeError('Use postgresql+psycopg or sqlite database URL')
        return value
    root = Path(os.getenv('VIETBIZ_DATA_DIR', './.vietbiz-data')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return 'sqlite:///' + str(root / 'vietbiz.sqlite3')


def build_engine(url):
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def enable_foreign_keys(dbapi_connection, _):
            dbapi_connection.execute('PRAGMA foreign_keys=ON')
    return engine


engine = build_engine(database_url())


class Transaction:
    """Bind existing fixed SQL with positional values; never interpolate values."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, parameters=()):
        parts = statement.split('?')
        if len(parts) - 1 != len(parameters):
            raise ValueError('SQL parameter count mismatch')
        sql = parts[0] + ''.join(f':p{i}' + part for i, part in enumerate(parts[1:]))
        result = self.connection.execute(text(sql), {f'p{i}': value for i, value in enumerate(parameters)})
        return result.mappings() if result.returns_rows else result


@contextmanager
def connection():
    with engine.begin() as conn:
        yield Transaction(conn)


def require_schema():
    with engine.connect() as conn:
        if not inspect(conn).has_table('alembic_version'):
            raise RuntimeError('Database requires migrations: run alembic upgrade head')
        revisions = conn.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
        if revisions != [SCHEMA_REVISION]:
            raise RuntimeError('Database schema revision mismatch; run migrations before startup')

```

FILE services/api/app/auth.py
```python
"""Bearer verification for a configured OIDC JWT access-token issuer."""
import json
import os
from hashlib import sha256
from urllib.parse import urlsplit
import jwt
from fastapi import HTTPException


class OIDCVerifier:
    def __init__(self, issuer, audience, jwks_url):
        for value in (issuer, jwks_url):
            parsed = urlsplit(value)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
                raise RuntimeError('OIDC issuer and JWKS URL must be trusted HTTPS URLs')
        if not audience:
            raise RuntimeError('OIDC audience is required')
        self.issuer, self.audience = issuer, audience
        self.jwks = jwt.PyJWKClient(jwks_url, timeout=5, lifespan=300)

    def verify(self, authorization):
        if not authorization:
            raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
        scheme, _, token = authorization.partition(' ')
        if scheme.lower() != 'bearer' or not token or len(token) > 16384:
            raise HTTPException(401, 'Invalid bearer token')
        try:
            header = jwt.get_unverified_header(token)
            if header.get('alg') != 'RS256' or not isinstance(header.get('kid'), str) or not header['kid']:
                raise jwt.InvalidTokenError('Unsupported signing header')
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=['RS256'], issuer=self.issuer,
                                audience=self.audience, options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']})
            if not isinstance(claims['sub'], str) or not claims['sub'].strip():
                raise jwt.InvalidTokenError('Empty subject')
        except (jwt.PyJWTError, ValueError, TypeError):
            raise HTTPException(401, 'Invalid or unverifiable bearer token', headers={'WWW-Authenticate': 'Bearer'}) from None
        # Domain-separated issuer + subject. Never link accounts by email/name.
        identity = json.dumps([claims['iss'], claims['sub']], separators=(',', ':'))
        return 'oidc:' + sha256(identity.encode()).hexdigest()


def configured_verifier():
    return OIDCVerifier(os.getenv('VIETBIZ_OIDC_ISSUER', ''),
                        os.getenv('VIETBIZ_OIDC_AUDIENCE', ''),
                        os.getenv('VIETBIZ_OIDC_JWKS_URL', ''))

```

FILE services/api/migrations/versions/0002_invitations.py
```python
"""Expiring, revocable invitations. Legacy pending invitations are invalidated."""
from alembic import op
import sqlalchemy as sa
revision = '0002_invitations'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('invitations', sa.Column('expires_at', sa.Text(), nullable=False,
                  server_default='1970-01-01T00:00:00+00:00'))
    op.add_column('invitations', sa.Column('revoked_at', sa.Text(), nullable=True))
    op.execute("UPDATE invitations SET revoked_at='1970-01-01T00:00:00+00:00' WHERE status='pending'")
    op.create_index('uq_active_invitation', 'invitations', ['organization_id', 'invitee_id'],
                    unique=True, sqlite_where=sa.text("status='pending' AND revoked_at IS NULL"),
                    postgresql_where=sa.text("status='pending' AND revoked_at IS NULL"))


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; restore a verified backup instead')

```


