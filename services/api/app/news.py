"""VietBiz News: metadata-only RSS intake, opt-in Vietnamese editorial publication."""
from __future__ import annotations
import hashlib, os, re, json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix='/v1/news', tags=['news'])
DB = Path(os.getenv('VIETBIZ_DATA_DIR', './.vietbiz-data')).resolve() / 'vietbiz.sqlite3'
# The operator must confirm redistribution rights before enabling a source.
SOURCES = {
  'novinky': {'name':'Novinky.cz','feed':'https://www.novinky.cz/rss2/','allowed_domains':('novinky.cz',), 'enabled':False},
}

from .database import connection, require_schema
require_schema()

def category_for(text: str) -> str:
    s = text.casefold()
    if any(w in s for w in ('eet','daň','dph','zákon','úřad','živnost','mzda','zaměstnan','pojištění')): return 'law'
    if any(w in s for w in ('obchod','firma','ekonom','cena','potravin','podnik')): return 'business'
    if any(w in s for w in ('festival','akce','koncert','výstava','praha')): return 'events'
    return 'general'

def extract_items(xml: bytes, source_id: str):
    if len(xml) > 2_000_000: raise ValueError('RSS is too large')
    root=ET.fromstring(xml)
    result=[]
    # RSS 2.0 or Atom feed, no article body retained
    if root.tag.endswith('rss'):
        for item in root.findall('./channel/item')[:50]:
            title=(item.findtext('title') or '').strip()
            url=(item.findtext('link') or '').strip()
            date=(item.findtext('pubDate') or '').strip()
            if title and url: result.append((title,url,date))
    else:
        ns={'a':'http://www.w3.org/2005/Atom'}
        for item in root.findall('a:entry',ns)[:50]:
            title=(item.findtext('a:title',default='',namespaces=ns)).strip()
            link=item.find('a:link',ns)
            url=link.attrib.get('href','') if link is not None else ''
            date=item.findtext('a:updated',default='',namespaces=ns)
            if title and url: result.append((title,url,date))
    return result

def import_feed(source_id:str, rss_bytes:bytes):
    source=SOURCES[source_id]
    added=0
    with connection() as db:
        for title,url,published in extract_items(rss_bytes,source_id):
            p=urlparse(url)
            host=(p.hostname or '').lower()
            if p.scheme!='https' or not any(host==h or host.endswith('.'+h) for h in source['allowed_domains']): continue
            item_id=hashlib.sha256(url.encode()).hexdigest()[:32]
            inserted=db.execute('''INSERT INTO news_items
                (id,source_id,source_title,url,published_at,category,retrieved_at)
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(url) DO NOTHING''',(item_id,source_id,title,url,published,category_for(title),datetime.now(timezone.utc).isoformat()))
            added += inserted.rowcount
    return added

def sync_source(source_id:str):
    if source_id not in SOURCES: raise ValueError('Unknown source')
    source=SOURCES[source_id]
    if not source['enabled']: raise PermissionError('Source disabled until permission/terms reviewed')
    # Never fetch arbitrary user-controlled addresses.
    with urlopen(Request(source['feed'],headers={'User-Agent':'VietBizNews/0.1 contact: operator'}),timeout=10) as r:
        raw=r.read(2_000_001)
    return import_feed(source_id,raw)

class EditorialReview(BaseModel):
    vi_title: str = Field(min_length=8,max_length=240)
    vi_summary: str = Field(min_length=25,max_length=750)
    # Reviewer must check accuracy, original link and rights.
    reviewer_verified: bool

@router.get('')
def list_news(category:str|None=None,q:str|None=Query(None,max_length=120),limit:int=Query(20,ge=1,le=50)):
    filters=["review_status='published'"]
    args=[]
    if category:
        filters.append('category=?'); args.append(category)
    if q:
        filters.append("(lower(vi_title) LIKE lower(?) ESCAPE '!' OR lower(vi_summary) LIKE lower(?) ESCAPE '!')")
        pattern = '%' + q.replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
        args.extend([pattern, pattern])
    sql='SELECT id,source_id,url,published_at,category,vi_title,vi_summary FROM news_items WHERE '+' AND '.join(filters)+' ORDER BY retrieved_at DESC LIMIT ?'
    with connection() as db:
        items=db.execute(sql,(*args,limit)).fetchall()
    return [dict(item) for item in items]

@router.get('/categories')
def categories():return ['general','business','law','events']

@router.get('/events')
def public_events(city:str|None=None,limit:int=Query(20,ge=1,le=50)):
    with connection() as db:
        if city:
            rows=db.execute('''SELECT id,title_vi,city,venue,starts_at,ends_at,source_url
              FROM news_events WHERE status='published' AND lower(city)=lower(?)
              ORDER BY starts_at LIMIT ?''',(city,limit)).fetchall()
        else:
            rows=db.execute('''SELECT id,title_vi,city,venue,starts_at,ends_at,source_url
              FROM news_events WHERE status='published' ORDER BY starts_at LIMIT ?''',(limit,)).fetchall()
    return [dict(x) for x in rows]

@router.get('/sources')
def public_sources():
    return [{'id':key,'name':source['name'],'enabled':source['enabled']} for key,source in SOURCES.items()]

@router.get('/{item_id}')
def news_detail(item_id:str):
    with connection() as db:
        row=db.execute("SELECT id,source_id,url,published_at,category,vi_title,vi_summary FROM news_items WHERE id=? AND review_status='published'",(item_id,)).fetchone()
    if not row:raise HTTPException(404,'News item not published')
    return dict(row)


# Sprint 03: drafts never become published without explicit editorial sign-off.
# The offline fallback is a classification/translation *stub*, NOT an AI translation.
def prepare_editorial_draft(item_id: str, translated_title: str, translated_summary: str, method: str='human'):
    if method not in ('human', 'approved_model'):
        raise ValueError('Translation must come from reviewed human text or configured approved model')
    if not translated_title.strip() or len(translated_summary.strip()) < 25:
        raise ValueError('Missing title or summary too short')
    with connection() as db:
        item=db.execute('SELECT id FROM news_items WHERE id=?',(item_id,)).fetchone()
        if item is None: raise ValueError('Unknown article')
        db.execute('''INSERT INTO news_editorial (item_id,draft_vi_title,draft_vi_summary,method)
          VALUES (?,?,?,?) ON CONFLICT(item_id) DO UPDATE SET
          draft_vi_title=excluded.draft_vi_title, draft_vi_summary=excluded.draft_vi_summary,
          method=excluded.method,reviewer=NULL,reviewed_at=NULL,legal_status='not_checked',authority_url=NULL''',
          (item_id,translated_title.strip(),translated_summary.strip(),method))
        db.execute("UPDATE news_items SET review_status='pending' WHERE id=?",(item_id,))

def publish_reviewed(item_id: str, reviewer: str, verified: bool, authority_url: str|None=None):
    if not verified or not reviewer.strip(): raise ValueError('Human reviewer sign-off required')
    with connection() as db:
        row=db.execute('''SELECT n.category,e.draft_vi_title,e.draft_vi_summary
          FROM news_items n JOIN news_editorial e ON e.item_id=n.id WHERE n.id=?''',(item_id,)).fetchone()
        if row is None: raise ValueError('Draft missing')
        if row['category']=='law':
            host=(urlparse(authority_url).hostname or '').lower() if authority_url else ''
            approved=('gov.cz','financnisprava.gov.cz','e-sbirka.gov.cz','cssz.cz','mpsv.cz','szpi.gov.cz','mzd.gov.cz','mpo.gov.cz','eet.gov.cz')
            if not any(host==x or host.endswith('.'+x) for x in approved):
                raise ValueError('Legal news requires an official authority URL')
        now=datetime.now(timezone.utc).isoformat()
        db.execute('''UPDATE news_editorial SET reviewer=?, reviewed_at=?,
          legal_status=?,authority_url=? WHERE item_id=?''',
          (reviewer.strip(),now,'official_source_checked' if authority_url else 'editor_checked',authority_url,item_id))
        db.execute('''UPDATE news_items SET vi_title=?,vi_summary=?,review_status='published' WHERE id=?''',
          (row['draft_vi_title'],row['draft_vi_summary'],item_id))
        db.execute('INSERT INTO news_review_log(item_id,action,actor,created_at,details) VALUES (?,?,?,?,?)',(item_id,'published',reviewer.strip(),now,json.dumps({'authority_url':authority_url})))

class EventDraft(BaseModel):
    title_vi: str=Field(min_length=6,max_length=200)
    city: str=Field(min_length=2,max_length=100)
    venue: str|None=None
    starts_at: datetime
    ends_at: datetime|None=None
    source_url: str

def save_event_draft(event: EventDraft):
    parsed=urlparse(event.source_url)
    if parsed.scheme!='https' or not parsed.hostname:
        raise ValueError('Event source URL must be HTTPS')
    if event.ends_at and event.ends_at < event.starts_at:
        raise ValueError('Event end must follow start')
    uid=hashlib.sha256((event.source_url+event.starts_at.isoformat()).encode()).hexdigest()[:32]
    with connection() as db:
        db.execute('''INSERT INTO news_events
          (id,title_vi,city,venue,starts_at,ends_at,source_url,created_at)
          VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING''',
          (uid,event.title_vi,event.city,event.venue,event.starts_at.isoformat(),
           event.ends_at.isoformat() if event.ends_at else None,event.source_url,
           datetime.now(timezone.utc).isoformat()))
    return uid

def publish_event(event_id: str, reviewer: str):
    if not reviewer.strip():raise ValueError('Reviewer required')
    with connection() as db:
        if not db.execute('SELECT 1 FROM news_events WHERE id=?',(event_id,)).fetchone():
            raise ValueError('Unknown event')
        db.execute("UPDATE news_events SET status='published' WHERE id=?",(event_id,))



# Offline translation pipeline adapter: caller supplies licensed text; result is never auto-published.
def queue_translation(item_id: str):
    with connection() as db:
        if not db.execute('SELECT 1 FROM news_items WHERE id=?',(item_id,)).fetchone():
            raise ValueError('Unknown article')
        now=datetime.now(timezone.utc).isoformat()
        db.execute("INSERT INTO news_translation_jobs(item_id,status,updated_at) VALUES (?,'queued',?) ON CONFLICT(item_id) DO UPDATE SET status='queued',error=NULL,updated_at=excluded.updated_at",(item_id,now))
    return item_id

def draft_with_adapter(item_id: str, adapter, input_text: str, *, rights_confirmed: bool=False):
    if not rights_confirmed:
        raise PermissionError('Confirm permission to process source text')
    if not callable(adapter):
        raise ValueError('Configured adapter must be callable')
    with connection() as db:
        if not db.execute('SELECT 1 FROM news_items WHERE id=?',(item_id,)).fetchone():
            raise ValueError('Unknown article')
    result=adapter(input_text)
    if not isinstance(result,dict) or not isinstance(result.get('title'),str) or not isinstance(result.get('summary'),str):
        raise ValueError('Adapter must return title and summary strings')
    prepare_editorial_draft(item_id,result['title'],result['summary'],'approved_model')
    with connection() as db:
        db.execute("UPDATE news_translation_jobs SET status='draft_ready',updated_at=? WHERE item_id=?",(datetime.now(timezone.utc).isoformat(),item_id))
    return {'item_id':item_id,'status':'draft_ready','review_required':True}

