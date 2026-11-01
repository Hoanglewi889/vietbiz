"""VietBiz local-first prototype, SQLite + HTTP stdlib. Not production accounting."""
import json, sqlite3, os, hashlib, uuid, datetime, mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('VIETBIZ_DATA',ROOT/'data'))
DB=DATA/'vietbiz.sqlite3'
MAX_BODY=8*1024*1024

def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    db=sqlite3.connect(DB)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, filename TEXT NOT NULL, mime TEXT NOT NULL, sha256 TEXT UNIQUE NOT NULL, path TEXT NOT NULL, amount_czk REAL, supplier TEXT, status TEXT NOT NULL DEFAULT 'needs_review', created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS cash_entries(id TEXT PRIMARY KEY, entry_date TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('income','expense')), amount_czk REAL NOT NULL CHECK(amount_czk > 0), description TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS shifts(id TEXT PRIMARY KEY, employee TEXT NOT NULL, shift_date TEXT NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS audit_events(id TEXT PRIMARY KEY, action TEXT NOT NULL, entity_id TEXT, payload TEXT, created_at TEXT NOT NULL);
    ''')
    return db

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def uid():return str(uuid.uuid4())
def audit(db,action,entity,payload=None):db.execute('INSERT INTO audit_events VALUES(?,?,?,?,?)',(uid(),action,entity,json.dumps(payload or {},ensure_ascii=False),now()))
def get_rows(db,table):return [dict(r) for r in db.execute('SELECT * FROM '+table+' ORDER BY created_at DESC LIMIT 300')]
def validate_date(s):datetime.date.fromisoformat(s);return s
def validate_time(s):datetime.time.fromisoformat(s);return s

def cash_create(v):
    d=validate_date(v['entry_date']);kind=v['kind'];a=float(v['amount_czk']);desc=str(v['description']).strip()
    if kind not in ('income','expense') or not (0<a<=1e9) or not desc:raise ValueError('Invalid cash entry')
    with connect() as db:
        ident=uid();db.execute('INSERT INTO cash_entries VALUES(?,?,?,?,?,?)',(ident,d,kind,round(a,2),desc,now()));audit(db,'cash.created',ident)
    return {'id':ident}
def shift_create(v):
    employee=str(v['employee']).strip();date=validate_date(v['shift_date']);start=validate_time(v['start_time']);end=validate_time(v['end_time'])
    if not employee or start>=end:raise ValueError('Invalid shift: end must be after start on same day')
    with connect() as db:
        ident=uid();db.execute('INSERT INTO shifts VALUES(?,?,?,?,?,?)',(ident,employee,date,start,end,now()));audit(db,'shift.created',ident)
    return {'id':ident}
def document_create(v):
    import base64
    name=Path(str(v['filename'])).name[:160]
    mime=str(v.get('mime',''))
    if mime not in ('application/pdf','image/jpeg','image/png','image/webp'):raise ValueError('Unsupported document type')
    blob=base64.b64decode(v['data_base64'],validate=True)
    if not blob or len(blob)>5*1024*1024:raise ValueError('Document must be 1 byte to 5MB')
    if mime=='application/pdf' and not blob.startswith(b'%PDF-'):raise ValueError('Invalid PDF header')
    if mime=='image/png' and not blob.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Invalid PNG header')
    if mime=='image/jpeg' and not blob.startswith(b'\xff\xd8\xff'):raise ValueError('Invalid JPEG header')
    if mime=='image/webp' and not (blob[:4]==b'RIFF' and blob[8:12]==b'WEBP'):raise ValueError('Invalid WebP header')
    sha=hashlib.sha256(blob).hexdigest()
    with connect() as db:
        existing=db.execute('SELECT id FROM documents WHERE sha256=?',(sha,)).fetchone()
        if existing:return {'id':existing['id'],'duplicate':True}
        ident=uid(); p=DATA/'uploads'/sha; p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(blob)
        db.execute('INSERT INTO documents(id,filename,mime,sha256,path,created_at) VALUES(?,?,?,?,?,?)',(ident,name,mime,sha,str(p),now()));audit(db,'document.uploaded',ident)
    return {'id':ident,'duplicate':False}
def document_review(v):
    ident=str(v['id']);status=v['status']
    if status not in ('approved','rejected','needs_review'):raise ValueError('Invalid status')
    supplier=str(v.get('supplier','')).strip()[:200]
    amount=v.get('amount_czk');amount=None if amount in ('',None) else round(float(amount),2)
    if amount is not None and (amount<0 or amount>1e9):raise ValueError('Invalid amount')
    with connect() as db:
        result=db.execute('UPDATE documents SET status=?, supplier=?, amount_czk=? WHERE id=?',(status,supplier,amount,ident))
        if result.rowcount!=1:raise ValueError('Document missing')
        audit(db,'document.reviewed',ident,{'status':status,'supplier':supplier,'amount_czk':amount})
    return {'id':ident,'status':status}
def overview():
    with connect() as db:
        d=get_rows(db,'documents');c=get_rows(db,'cash_entries');s=get_rows(db,'shifts')
        return {'documents':d,'cash_entries':c,'shifts':s,'cash_balance_czk':round(sum(x['amount_czk']*(1 if x['kind']=='income' else -1) for x in c),2),'pending_documents':sum(x['status']=='needs_review' for x in d),'note':'Local demo data, not accounting-confirmed'}

class Handler(BaseHTTPRequestHandler):
    def respond(self,status,obj):
        b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(b)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/overview':return self.respond(200,overview())
        if path=='/api/health':return self.respond(200,{'ok':True,'prototype':True})
        if path not in ('/','/app.js','/style.css'):return self.respond(404,{'error':'Not found'})
        filepath=ROOT/'web'/('index.html' if path=='/' else path[1:]);body=filepath.read_bytes()
        self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(filepath)[0] or 'text/plain');self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def do_POST(self):
        path=urlparse(self.path).path
        funcs={'/api/cash':cash_create,'/api/shifts':shift_create,'/api/documents':document_create,'/api/documents/review':document_review}
        if path not in funcs:return self.respond(404,{'error':'Not found'})
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n<1 or n>MAX_BODY:return self.respond(413,{'error':'Invalid request size'})
            payload=json.loads(self.rfile.read(n));return self.respond(201,funcs[path](payload))
        except (ValueError,KeyError,TypeError,UnicodeError) as e:return self.respond(400,{'error':str(e)})
        except Exception:return self.respond(500,{'error':'Internal error'})
if __name__=='__main__':
    connect().close()
    port=int(os.environ.get('PORT',8765));print(f'VietBiz demo at http://127.0.0.1:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
