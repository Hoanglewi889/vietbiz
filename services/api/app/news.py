"""VietBiz News: metadata-only RSS intake, opt-in Vietnamese editorial publication.

Owner decision G (12.11.2026): news may come from Czech, Vietnamese and international outlets
and is written again in Vietnamese. What that allows and what it does not:

- Intake keeps only each article's headline, link and date (no body, no image). The headline
  stays inside VietBiz for the editor; it is never shown to readers.
- The editor writes a new Vietnamese title and summary from the facts, in their own words,
  optionally from several articles, and cites every source with a link. Facts and "denní
  zpráva" are not protected works (§ 2 odst. 6 autorského zákona); the press publisher's right
  (§ 87b) does not cover hyperlinks, single words or very short extracts. Copying or lightly
  reworking an article, even with "Nguồn: …", is not allowed — in Czechia (§ 87b, 2 years from
  publication) nor under Vietnam's Decree 174/2026 for Vietnamese outlets.
- A draft that repeats a run of the source headline is refused (`copies_source`), the editor
  declares the text is their own (`own_words`), and a reviewer signs off before publication.
- Legal news still needs an official authority link (ČSSZ, Finanční správa, …).
"""
from __future__ import annotations
import hashlib, os, re, json, unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix='/v1/news', tags=['news'])
DB = Path(os.getenv('VIETBIZ_DATA_DIR', './.vietbiz-data')).resolve() / 'vietbiz.sqlite3'
# Headline + link + date only (see the module note). Feeds checked 12.11.2026. A source can be
# switched off here, e.g. when its owner objects.
SOURCES = {
  'novinky': {'name':'Novinky.cz','group':'cz','feed':'https://www.novinky.cz/rss2/','allowed_domains':('novinky.cz',),'enabled':True},
  'seznamzpravy': {'name':'Seznam Zprávy','group':'cz','feed':'https://www.seznamzpravy.cz/rss','allowed_domains':('seznamzpravy.cz',),'enabled':True},
  'irozhlas': {'name':'iROZHLAS','group':'cz','feed':'https://www.irozhlas.cz/rss/irozhlas','allowed_domains':('irozhlas.cz',),'enabled':True},
  'ct24': {'name':'ČT24','group':'cz','feed':'https://ct24.ceskatelevize.cz/rss/hlavni-zpravy','allowed_domains':('ceskatelevize.cz',),'enabled':True},
  'vnexpress': {'name':'VnExpress','group':'vn','feed':'https://vnexpress.net/rss/tin-moi-nhat.rss','allowed_domains':('vnexpress.net',),'enabled':True},
  'tuoitre': {'name':'Tuổi Trẻ','group':'vn','feed':'https://tuoitre.vn/rss/tin-moi-nhat.rss','allowed_domains':('tuoitre.vn',),'enabled':True},
  'vietnamplus': {'name':'Vietnam+ (TTXVN)','group':'vn','feed':'https://www.vietnamplus.vn/rss/home.rss','allowed_domains':('vietnamplus.vn',),'enabled':True},
  'radioprague': {'name':'Radio Prague International','group':'intl','feed':'https://english.radio.cz/rcz-rss/en','allowed_domains':('radio.cz',),'enabled':True},
}
MAX_EXTRA_SOURCES = 4
COPY_RUN = 6  # words in a row taken from a source headline that make a draft a copy

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
    # Security review 11.11.2026: feeds never need a DTD; refuse one like the ISDOC import does.
    if b'<!DOCTYPE' in xml.upper() or b'<!ENTITY' in xml.upper(): raise ValueError('DTD not allowed in feed')
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
        return _with_sources(db,[dict(item) for item in items])

def _source_name(url: str) -> str:
    host=(urlparse(url).hostname or '').lower()
    for source in SOURCES.values():
        if any(host==h or host.endswith('.'+h) for h in source['allowed_domains']):
            return source['name']
    return host.removeprefix('www.')

def _with_sources(db, items: list[dict]) -> list[dict]:
    """Every source an item was written from, main one first, each with its outlet's name."""
    extra={}
    if items:
        marks=','.join('?'*len(items))
        for row in db.execute(f'SELECT item_id,url FROM news_item_links WHERE item_id IN ({marks}) ORDER BY item_id,position',
                              [i['id'] for i in items]).fetchall():
            extra.setdefault(row['item_id'],[]).append(row['url'])
    for item in items:
        item['source_name']=SOURCES.get(item['source_id'],{}).get('name') or _source_name(item['url'])
        item['sources']=[{'name':item['source_name'],'url':item['url']}]+[{'name':_source_name(u),'url':u} for u in extra.get(item['id'],[])]
    return items

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
    return [{'id':key,'name':source['name'],'group':source['group'],'enabled':source['enabled']} for key,source in SOURCES.items()]

@router.get('/{item_id}')
def news_detail(item_id:str):
    with connection() as db:
        row=db.execute("SELECT id,source_id,url,published_at,category,vi_title,vi_summary FROM news_items WHERE id=? AND review_status='published'",(item_id,)).fetchone()
        if not row:raise HTTPException(404,'News item not published')
        return _with_sources(db,[dict(row)])[0]


# Sprint 03: drafts never become published without explicit editorial sign-off.
# The offline fallback is a classification/translation *stub*, NOT an AI translation.
def _words(text: str) -> list[str]:
    return re.findall(r'\w+', unicodedata.normalize('NFC', text).casefold())

def copies_source(source_title: str, *texts: str, run: int = COPY_RUN) -> bool:
    """True when a text repeats the source headline: the whole headline, or `run` of its words
    in a row (fewer for a short headline, never under four)."""
    head=_words(source_title)
    if len(head) < 4:
        return False
    n=min(run, len(head))
    grams={tuple(head[i:i+n]) for i in range(len(head)-n+1)}
    for text in texts:
        words=_words(text)
        if any(tuple(words[i:i+n]) in grams for i in range(len(words)-n+1)):
            return True
    return False

def _source_links(urls) -> list[str]:
    links=[]
    for url in urls or ():
        url=(url or '').strip()
        parsed=urlparse(url)
        if parsed.scheme!='https' or not parsed.hostname:
            raise ValueError('Every source must be an https link')
        if url not in links: links.append(url)
    if len(links) > MAX_EXTRA_SOURCES:
        raise ValueError(f'At most {MAX_EXTRA_SOURCES} further sources')
    return links

def prepare_editorial_draft(item_id: str, translated_title: str, translated_summary: str, method: str='human', *,
                            own_words: bool=False, extra_sources=(), editor: str='editor'):
    """Save a Vietnamese draft for review. A human editor declares `own_words` (written from the
    facts, not translated or pasted from the article); every draft is checked against the source
    headline and refused when it repeats it."""
    if method not in ('human', 'approved_model'):
        raise ValueError('Translation must come from reviewed human text or configured approved model')
    if not translated_title.strip() or len(translated_summary.strip()) < 25:
        raise ValueError('Missing title or summary too short')
    if method=='human' and not own_words:
        raise ValueError('Write the news in your own words and confirm it (own_words)')
    links=_source_links(extra_sources)
    with connection() as db:
        item=db.execute('SELECT id,source_title,url FROM news_items WHERE id=?',(item_id,)).fetchone()
        if item is None: raise ValueError('Unknown article')
        if item['url'] in links: links.remove(item['url'])
        if copies_source(item['source_title'],translated_title,translated_summary):
            raise ValueError('The draft repeats the source headline; write it in your own words')
        db.execute('''INSERT INTO news_editorial (item_id,draft_vi_title,draft_vi_summary,method)
          VALUES (?,?,?,?) ON CONFLICT(item_id) DO UPDATE SET
          draft_vi_title=excluded.draft_vi_title, draft_vi_summary=excluded.draft_vi_summary,
          method=excluded.method,reviewer=NULL,reviewed_at=NULL,legal_status='not_checked',authority_url=NULL''',
          (item_id,translated_title.strip(),translated_summary.strip(),method))
        db.execute("UPDATE news_items SET review_status='pending' WHERE id=?",(item_id,))
        db.execute('DELETE FROM news_item_links WHERE item_id=?',(item_id,))
        for position,url in enumerate(links,1):
            db.execute('INSERT INTO news_item_links(item_id,position,url) VALUES (?,?,?)',(item_id,position,url))
        db.execute('INSERT INTO news_review_log(item_id,action,actor,created_at,details) VALUES (?,?,?,?,?)',
                   (item_id,'drafted',editor,datetime.now(timezone.utc).isoformat(),
                    json.dumps({'method':method,'own_words':bool(own_words),'sources':1+len(links)})))

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

