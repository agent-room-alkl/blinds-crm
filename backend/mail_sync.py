"""Read-only IMAP collection: UID checkpoints, PEEK fetches and message deduplication."""
import os,json,imaplib,ssl,hashlib,re
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from html.parser import HTMLParser

def configured():return all(os.getenv(k,'').strip() for k in ('IMAP_HOST','IMAP_USERNAME','IMAP_PASSWORD'))

class Text(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
        if tag in ('p','div','br','li'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.hidden=max(0,self.hidden-1)
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)

def parse_message(raw):
    message=BytesParser(policy=policy.default).parsebytes(raw)
    part=message.get_body(preferencelist=('plain','html'))
    body=part.get_content() if part else ''
    if part and part.get_content_type()=='text/html':
        text=Text();text.feed(body);body=''.join(text.parts)
    if not body.strip():body='[Message has no readable text body]'
    return {'external_id':str(message.get('Message-ID') or 'imap:'+hashlib.sha256(raw).hexdigest())[:500],'sender':parseaddr(str(message.get('From','')))[1],'recipient':parseaddr(str(message.get('To','')))[1],'subject':str(message.get('Subject',''))[:300],'body':body[:20000],'references':re.findall(r'<[^>]+>',str(message.get('In-Reply-To',''))+' '+str(message.get('References','')))[:30]}

def collect(db,dump,ingest,model):
    if not configured():return 0
    account=hashlib.sha256((os.environ['IMAP_HOST']+os.environ['IMAP_USERNAME']+os.getenv('IMAP_FOLDER','INBOX')).encode()).hexdigest()
    count=0
    with imaplib.IMAP4_SSL(os.environ['IMAP_HOST'],int(os.getenv('IMAP_PORT','993')),ssl_context=ssl.create_default_context(),timeout=20) as client:
        client.login(os.environ['IMAP_USERNAME'],os.environ['IMAP_PASSWORD'])
        status,_=client.select(os.getenv('IMAP_FOLDER','INBOX'),readonly=True)
        if status!='OK':raise RuntimeError('Could not select the receiving mailbox')
        validity=str(client.response('UIDVALIDITY')[1])
        with db() as c:
            row=c.execute('SELECT data FROM integration_state WHERE id=?',(account,)).fetchone();saved=json.loads(row['data']) if row else {}
        since=saved.get('last_uid',0) if saved.get('validity')==validity else 0
        status,rows=client.uid('search',None,'ALL')
        if status!='OK':raise RuntimeError('Could not search the receiving mailbox')
        ids=[int(x) for x in rows[0].split() if int(x)>since]
        # Initial connection imports only the newest ten; subsequent runs catch up ten at a time.
        if not since:ids=ids[-10:]
        for uid in ids[:10]:
            status,data=client.uid('fetch',str(uid),'(BODY.PEEK[])')
            if status!='OK':break
            raw=next((x[1] for x in data if isinstance(x,tuple)),None)
            if not raw:break
            try:ingest(model(**parse_message(raw)))
            except Exception:break # Do not advance past a message that could not be archived.
            count+=1
            with db() as c:
                c.execute('INSERT INTO integration_state(id,data) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(account,dump({'validity':validity,'last_uid':uid})))
    return count
