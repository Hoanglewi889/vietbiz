"""Safe local editorial CLI (never expose as unauthenticated HTTP endpoint)."""
import argparse
from app.news import prepare_editorial_draft,publish_reviewed,save_event_draft,publish_event,EventDraft

def main():
    parser=argparse.ArgumentParser(description='VietBiz News editorial tools, offline')
    sub=parser.add_subparsers(dest='cmd',required=True)
    draft=sub.add_parser('draft');draft.add_argument('id');draft.add_argument('--title',required=True);draft.add_argument('--summary',required=True)
    draft.add_argument('--source',action='append',default=[],help='a further article the news was written from (https)')
    draft.add_argument('--own-words',action='store_true',help='I wrote this from the facts in my own words, not translated or pasted')
    draft.add_argument('--editor',default='editor')
    pub=sub.add_parser('publish');pub.add_argument('id');pub.add_argument('--reviewer',required=True);pub.add_argument('--authority-url')
    event=sub.add_parser('event');event.add_argument('--title',required=True);event.add_argument('--city',required=True);event.add_argument('--starts-at',required=True);event.add_argument('--source-url',required=True);event.add_argument('--venue')
    pe=sub.add_parser('publish-event');pe.add_argument('id');pe.add_argument('--reviewer',required=True)
    a=parser.parse_args()
    if a.cmd=='draft':prepare_editorial_draft(a.id,a.title,a.summary,own_words=a.own_words,extra_sources=a.source,editor=a.editor)
    elif a.cmd=='publish':publish_reviewed(a.id,a.reviewer,True,a.authority_url)
    elif a.cmd=='event':print(save_event_draft(EventDraft(title_vi=a.title,city=a.city,starts_at=a.starts_at,source_url=a.source_url,venue=a.venue)))
    elif a.cmd=='publish-event':publish_event(a.id,a.reviewer)
    print('OK')
if __name__=='__main__':main()
