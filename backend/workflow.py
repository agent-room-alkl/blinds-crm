"""Persistent quote drafts and automatically archived project communication."""
import json,uuid,hashlib,os,hmac
from datetime import datetime,timedelta
from fastapi import Depends,HTTPException,Header
from pydantic import BaseModel,Field,ValidationError
import ai_client

class DraftInput(BaseModel):
    data:dict
    revision:int=Field(ge=1)
class Revision(BaseModel):
    revision:int=Field(ge=1)
class StartDraft(BaseModel):
    quote_id:int|None=None
class EmailInput(BaseModel):
    recipient:str=Field(min_length=3,max_length=254)
    subject:str=Field(min_length=1,max_length=200)
    body:str=Field(min_length=1,max_length=10000)
    send_key:str=Field(min_length=16,max_length=100)
    quote_id:int|None=None
    version:int|None=None
class GenerateEmail(BaseModel):
    goal:str=Field(min_length=1,max_length=1000)
    locale:str='zh'
    quote_id:int|None=None
    version:int|None=None
class NoteInput(BaseModel):
    kind:str=Field(pattern='^(phone|wechat|note)$')
    body:str=Field(min_length=1,max_length=10000)
class Inbound(BaseModel):
    external_id:str=Field(min_length=1,max_length=500)
    sender:str=Field(max_length=254)
    recipient:str=Field(default='',max_length=254)
    subject:str=Field(max_length=300)
    body:str=Field(min_length=1,max_length=20000)
    references:list[str]=Field(default_factory=list,max_length=30)

def register(app,s):
    def project(c,iid):
        row=c.execute('SELECT * FROM inquiries WHERE id=?',(iid,)).fetchone()
        if not row:raise HTTPException(404,'Inquiry not found')
        return json.loads(row['data'])
    def draft_dict(row):
        d=dict(row);d['data']=json.loads(d['data']);return d
    def comm_dict(row):
        d=dict(row);d['analysis']=json.loads(d['analysis']);return d
    def get_draft(c,did):
        row=c.execute('SELECT * FROM quote_drafts WHERE id=?',(did,)).fetchone()
        if not row:raise HTTPException(404,'Draft not found')
        return row

    @app.get('/api/quote-drafts',dependencies=[Depends(s.auth)])
    def drafts():
        with s.db() as c:return [draft_dict(r) for r in c.execute('SELECT * FROM quote_drafts WHERE published_version_id IS NULL ORDER BY updated_at DESC')]

    @app.get('/api/quote-drafts/{did}',dependencies=[Depends(s.auth)])
    def read_draft(did:str):
        with s.db() as c:return draft_dict(get_draft(c,did))

    @app.post('/api/inquiries/{iid}/quote-draft')
    def start_draft(iid:int,body:StartDraft,actor=Depends(s.auth)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE');iq=project(c,iid)
            if body.quote_id:
                q=c.execute('SELECT * FROM quotes WHERE id=? AND inquiry_id=?',(body.quote_id,iid)).fetchone()
                if not q:raise HTTPException(404,'Quote not found')
                if c.execute('SELECT id FROM orders WHERE version_id IN (SELECT id FROM quote_versions WHERE quote_id=?)',(body.quote_id,)).fetchone():raise HTTPException(409,'Accepted quote is locked')
                existing=c.execute('SELECT * FROM quote_drafts WHERE inquiry_id=? AND quote_id=? AND published_version_id IS NULL',(iid,body.quote_id)).fetchone()
            else:existing=c.execute('SELECT * FROM quote_drafts WHERE inquiry_id=? AND quote_id IS NULL AND published_version_id IS NULL',(iid,)).fetchone()
            if existing:return draft_dict(existing)
            if body.quote_id:
                version=c.execute('SELECT * FROM quote_versions WHERE quote_id=? ORDER BY version DESC LIMIT 1',(body.quote_id,)).fetchone()
                data=json.loads(version['data']);data['base_version']=version['version']
            else:
                p=c.execute('SELECT data FROM products WHERE id=?',(iq.get('product_id'),)).fetchone();p=json.loads(p['data']) if p else {}
                zh=iq.get('locale')=='zh'
                data={'inquiry_id':iid,'locale':iq.get('locale','en'),'currency':'NZD','valid_until':str(s.business_now().date()+timedelta(days=30)),'discount':0,'shipping':0,'tax':0,'terms':'','lines':[{'product_id':iq.get('product_id') or '', 'width':iq.get('width') or '', 'height':iq.get('height') or '', 'unit':iq.get('unit') or p.get('unit','mm'),'material':p.get('material_zh' if zh else 'material_en',''),'color':p.get('colors',[''])[0] if len(p.get('colors',[]))==1 else '', 'control':p.get('controls',[''])[0] if len(p.get('controls',[]))==1 else '', 'quantity':iq.get('quantity') or 1,'unit_price':''}]}
            did=uuid.uuid4().hex
            c.execute('INSERT INTO quote_drafts(id,inquiry_id,quote_id,data,updated_at,actor) VALUES(?,?,?,?,?,?)',(did,iid,body.quote_id,s.dump(data),s.now(),actor))
            return draft_dict(get_draft(c,did))

    @app.post('/api/quote-drafts/{did}')
    def save_draft(did:str,body:DraftInput,actor=Depends(s.auth)):
        if len(json.dumps(body.data))>120000 or not isinstance(body.data.get('lines'),list) or not 1<=len(body.data['lines'])<=100:raise HTTPException(422,'Invalid draft size')
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE');row=get_draft(c,did)
            if row['published_version_id']:raise HTTPException(409,'This draft is already finalized')
            if row['revision']!=body.revision:raise HTTPException(409,'Draft changed in another session. Reload before editing.')
            allowed={'locale','currency','valid_until','discount','shipping','tax','terms','lines'}
            data={k:v for k,v in body.data.items() if k in allowed};data['inquiry_id']=row['inquiry_id']
            previous=json.loads(row['data'])
            if 'base_version' in previous:data['base_version']=previous['base_version']
            c.execute('UPDATE quote_drafts SET data=?,revision=revision+1,updated_at=?,actor=? WHERE id=?',(s.dump(data),s.now(),actor,did))
            return draft_dict(get_draft(c,did))

    @app.post('/api/quote-drafts/{did}/publish')
    def publish(did:str,body:Revision,actor=Depends(s.auth)):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE');row=get_draft(c,did)
            if row['published_version_id']:return s.version_dict(c,c.execute('SELECT * FROM quote_versions WHERE id=?',(row['published_version_id'],)).fetchone())
            if row['revision']!=body.revision:raise HTTPException(409,'Draft changed. Reload before finalizing.')
            data=json.loads(row['data'])
            try:validated=s.QuoteBody.model_validate(data)
            except ValidationError as exc:raise HTTPException(422,[{'loc':e['loc'],'msg':e['msg']} for e in exc.errors()]) from None
            for amount in [line.unit_price for line in validated.lines]+[validated.discount,validated.shipping,validated.tax]:
                if amount.as_tuple().exponent < -2:raise HTTPException(422,'Amounts support at most two decimal places')
            qid=row['quote_id'];n=1
            if qid:
                if c.execute('SELECT id FROM orders WHERE version_id IN (SELECT id FROM quote_versions WHERE quote_id=?)',(qid,)).fetchone():raise HTTPException(409,'Accepted quote is locked')
                latest=c.execute('SELECT MAX(version) FROM quote_versions WHERE quote_id=?',(qid,)).fetchone()[0]
                if data.get('base_version')!=latest:raise HTTPException(409,'A newer quote version exists. Start a new revision.')
                n=latest+1
            else:qid=c.execute('INSERT INTO quotes(inquiry_id,created_at) VALUES(?,?)',(row['inquiry_id'],s.now())).lastrowid
            result=s.store_version(c,qid,n,s.quote_data(c,validated))
            c.execute('UPDATE quote_drafts SET published_version_id=?,updated_at=? WHERE id=?',(result['id'],s.now(),did))
            c.execute("UPDATE inquiries SET status='quoted' WHERE id=? AND status!='won'",(row['inquiry_id'],))
            return result

    def analyze_message(mid):
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM communications WHERE id=?',(mid,)).fetchone()
            if not row:return
            previous=json.loads(row['analysis'])
            if previous.get('state')=='ready':return
            if row['status'] not in ('smtp_accepted','received','recorded'):return
            if not ai_client.configuration()['configured']:
                c.execute('UPDATE communications SET analysis=? WHERE id=?',(s.dump({'state':'unconfigured','summary':'','facts':[],'tasks':[]}),mid));return
            if previous.get('state')=='processing' and previous.get('started_at'):
                try:
                    if (datetime.fromisoformat(s.now())-datetime.fromisoformat(previous['started_at'])).total_seconds()<120:return
                except ValueError:pass
            c.execute('UPDATE communications SET analysis=? WHERE id=?',(s.dump({'state':'processing','started_at':s.now()}),mid))
            iq=project(c,row['inquiry_id']) if row['inquiry_id'] else {}
        try:
            result=ai_client.analyze(row['subject'],row['body'],iq.get('locale','zh'));result.update(state='ready',model=ai_client.configuration()['model'])
            for task in result['tasks']:
                due=task.get('due_at')
                if due:
                    try:
                        datetime.fromisoformat(due)
                        if due[:10] not in task['evidence']:task['due_at']=None
                    except ValueError:task['due_at']=None
        except Exception:result={'state':'error','retry_at':(datetime.fromisoformat(s.now())+timedelta(minutes=5)).isoformat(),'summary':'','facts':[],'tasks':[]}
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE');c.execute('UPDATE communications SET analysis=? WHERE id=?',(s.dump(result),mid))
            if row['inquiry_id'] and result['state']=='ready' and not c.execute('SELECT id FROM project_tasks WHERE communication_id=?',(mid,)).fetchone():
                for i,task in enumerate(result['tasks']):
                    tid=hashlib.sha256((mid+str(i)).encode()).hexdigest()
                    c.execute('INSERT OR IGNORE INTO project_tasks(id,inquiry_id,communication_id,title,due_at,status,created_at) VALUES(?,?,?,?,?,?,?)',(tid,row['inquiry_id'],mid,task['title'],task.get('due_at'),'todo',s.now()))

    @app.get('/api/inquiries/{iid}/workspace',dependencies=[Depends(s.auth)])
    def workspace(iid:int):
        with s.db() as c:
            project(c,iid)
            communications=[comm_dict(r) for r in c.execute('SELECT * FROM communications WHERE inquiry_id=? ORDER BY created_at DESC',(iid,))]
            legacy=[dict(r) for r in c.execute('SELECT * FROM followups WHERE inquiry_id=? ORDER BY id DESC',(iid,))]
            tasks=[dict(r) for r in c.execute('SELECT * FROM project_tasks WHERE inquiry_id=? ORDER BY created_at DESC',(iid,))]
            return {'communications':communications,'legacy':legacy,'tasks':tasks,'ai':ai_client.configuration()}

    @app.post('/api/inquiries/{iid}/communications/note')
    def note(iid:int,body:NoteInput,actor=Depends(s.auth)):
        mid=uuid.uuid4().hex
        with s.db() as c:
            project(c,iid)
            c.execute('INSERT INTO communications(id,inquiry_id,kind,direction,sender,recipient,subject,body,status,analysis,created_at,actor) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(mid,iid,body.kind,'internal',actor,'','',body.body,'recorded',s.dump({'state':'pending'}),s.now(),actor))
        analyze_message(mid)
        with s.db() as c:return comm_dict(c.execute('SELECT * FROM communications WHERE id=?',(mid,)).fetchone())

    @app.post('/api/project-tasks/{tid}/complete')
    def complete_task(tid:str,_actor=Depends(s.auth)):
        with s.db() as c:
            if not c.execute('SELECT id FROM project_tasks WHERE id=?',(tid,)).fetchone():raise HTTPException(404,'Task not found')
            c.execute("UPDATE project_tasks SET status='done' WHERE id=?",(tid,));return {'ok':True}

    @app.post('/api/inquiries/{iid}/communications/draft-email')
    def email_draft(iid:int,body:GenerateEmail,_actor=Depends(s.auth)):
        with s.db() as c:
            iq=project(c,iid);context={k:iq.get(k) for k in ('company','contact_name','product_id','width','height','unit','quantity','expected_date')}
            if body.quote_id:
                q=c.execute('SELECT inquiry_id FROM quotes WHERE id=?',(body.quote_id,)).fetchone()
                if not q or q['inquiry_id']!=iid:raise HTTPException(422,'Quote does not belong to this project')
                v=s.version_dict(c,s.get_version(c,body.quote_id,body.version));context['quote']={k:v[k] for k in ('quote_id','version','currency','total','valid_until','lines','terms')}
            context['recent_customer_messages']=[{'subject':r['subject'],'body':r['body'][:5000]} for r in c.execute("SELECT subject,body FROM communications WHERE inquiry_id=? AND direction='inbound' ORDER BY created_at DESC LIMIT 3",(iid,))]
        try:return ai_client.draft_email(context,body.goal,body.locale)
        except ai_client.AIError as exc:raise HTTPException(503,str(exc)) from None

    @app.post('/api/inquiries/{iid}/communications/email')
    def email(iid:int,body:EmailInput,actor=Depends(s.auth)):
        from email_service import configuration,address,send_email
        try:address(body.recipient)
        except ValueError:raise HTTPException(422,'Invalid email address') from None
        if '\n' in body.subject or '\r' in body.subject:raise HTTPException(422,'Invalid email subject')
        if not configuration()[0]['configured']:raise HTTPException(503,'Configure SMTP first')
        attachments=[];mid=uuid.uuid4().hex
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE');project(c,iid)
            existing=c.execute('SELECT * FROM communications WHERE send_key=?',(body.send_key,)).fetchone()
            if existing:
                if existing['inquiry_id']!=iid or any(existing[k]!=getattr(body,k) for k in ('recipient','subject','body','quote_id','version')):raise HTTPException(409,'Send key was already used for another message')
                return comm_dict(existing)
            if body.quote_id:
                q=c.execute('SELECT inquiry_id FROM quotes WHERE id=?',(body.quote_id,)).fetchone()
                if not q or q['inquiry_id']!=iid or not body.version:raise HTTPException(422,'Invalid quote attachment')
                latest=c.execute('SELECT MAX(version) FROM quote_versions WHERE quote_id=?',(body.quote_id,)).fetchone()[0]
                if latest!=body.version:raise HTTPException(409,'Send only the current quote version')
                v=s.version_dict(c,s.get_version(c,body.quote_id,body.version))
                if v['valid_until']<str(s.business_now().date()):raise HTTPException(409,'Quote expired')
                attachments=[(f'VERA-Q{body.quote_id}-v{body.version}.html',s.export(body.quote_id,body.version,v['locale']).encode(),'text','html')]
            c.execute('INSERT INTO communications(id,inquiry_id,kind,direction,sender,recipient,subject,body,status,send_key,quote_id,version,analysis,created_at,actor) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(mid,iid,'email','outbound',configuration()[0]['sender'],body.recipient,body.subject,body.body,'sending',body.send_key,body.quote_id,body.version,s.dump({'state':'pending'}),s.now(),actor))
        try:
            external=send_email(body.recipient,body.subject,body.body,attachments=attachments);status='smtp_accepted'
        except Exception:external=None;status='unknown'
        with s.db() as c:
            c.execute('UPDATE communications SET status=?,external_id=? WHERE id=?',(status,external,mid))
            if status=='smtp_accepted':c.execute("UPDATE inquiries SET status='contacted' WHERE id=? AND status='new'",(iid,))
        if status=='smtp_accepted':analyze_message(mid)
        with s.db() as c:return comm_dict(c.execute('SELECT * FROM communications WHERE id=?',(mid,)).fetchone())

    def ingest(body):
        from email_service import address
        try:address(body.sender)
        except ValueError:raise HTTPException(422,'Invalid sender') from None
        with s.db() as c:
            c.execute('BEGIN IMMEDIATE')
            existing=c.execute('SELECT * FROM communications WHERE external_id=?',(body.external_id,)).fetchone()
            if existing:return comm_dict(existing)
            iid=None
            for ref in body.references:
                row=c.execute('SELECT inquiry_id FROM communications WHERE external_id=?',(ref,)).fetchone()
                if row and row['inquiry_id']:iid=row['inquiry_id'];break
            if not iid:
                import re
                matches=[]
                for row in c.execute('SELECT id,data FROM inquiries'):
                    channel=json.loads(row['data']).get('channel','')
                    if body.sender.lower() in [a.lower() for a in re.findall(r'[^\s/<>]+@[^\s/<>]+\.[^\s/<>]+',channel)]:matches.append(row['id'])
                if len(matches)==1:iid=matches[0]
            mid=uuid.uuid4().hex
            c.execute('INSERT INTO communications(id,inquiry_id,kind,direction,sender,recipient,subject,body,status,external_id,analysis,created_at,actor) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(mid,iid,'email','inbound',body.sender,body.recipient,body.subject,body.body,'received',body.external_id,s.dump({'state':'pending'}),s.now(),'mail-sync'))
        return {'id':mid,'inquiry_id':iid}

    def job_auth(authorization:str|None=Header(default=None)):
        secret=os.getenv('CRON_SECRET','')
        if len(secret)<24:raise HTTPException(503,'Configure a mail integration secret')
        if not authorization or not hmac.compare_digest(authorization,'Bearer '+secret):raise HTTPException(401,'Unauthorized integration')

    @app.post('/api/integrations/mail/inbound',dependencies=[Depends(job_auth)])
    def receive(body:Inbound):
        result=ingest(body);analyze_message(result['id']);return result

    @app.get('/api/communications/unassigned',dependencies=[Depends(s.auth)])
    def unassigned():
        with s.db() as c:return [comm_dict(r) for r in c.execute('SELECT * FROM communications WHERE inquiry_id IS NULL ORDER BY created_at DESC LIMIT 100')]

    @app.post('/api/communications/{mid}/assign')
    def assign(mid:str,body:dict,_actor=Depends(s.auth)):
        iid=body.get('inquiry_id')
        with s.db() as c:
            project(c,iid);row=c.execute('SELECT * FROM communications WHERE id=?',(mid,)).fetchone()
            if not row:raise HTTPException(404,'Message not found')
            if row['inquiry_id']:raise HTTPException(409,'Message already linked')
            c.execute('UPDATE communications SET inquiry_id=?,analysis=? WHERE id=?',(iid,s.dump({'state':'pending'}),mid))
        analyze_message(mid);return {'ok':True}

    def run_pending():
        with s.db() as c:
            rows=[]
            for row in c.execute("SELECT id,analysis FROM communications WHERE inquiry_id IS NOT NULL AND status IN ('smtp_accepted','received','recorded') ORDER BY created_at"):
                analysis=json.loads(row['analysis']);state=analysis.get('state')
                if state=='error' and analysis.get('retry_at','')>s.now():continue
                if state in ('pending','unconfigured','error'):rows.append(row['id'])
                elif state=='processing':
                    try:
                        if (datetime.fromisoformat(s.now())-datetime.fromisoformat(analysis['started_at'])).total_seconds()>=120:rows.append(row['id'])
                    except (KeyError,ValueError):rows.append(row['id'])
                if len(rows)>=2:break
        if ai_client.configuration()['configured']:
            for mid in rows:analyze_message(mid)
        return len(rows)

    def sync():
        from mail_sync import collect
        count=collect(s.db,s.dump,ingest,Inbound)
        run_pending();return {'received':count}

    @app.get('/api/jobs/mail-sync',dependencies=[Depends(job_auth)])
    def scheduled_sync():return sync()

    @app.post('/api/mail/sync',dependencies=[Depends(s.require_admin)])
    def manual_sync():return sync()

    @app.get('/api/integrations/status',dependencies=[Depends(s.auth)])
    def integrations():
        from email_service import configuration
        from mail_sync import configured
        return {'ai':ai_client.configuration(),'smtp':configuration()[0],'imap':{'configured':configured()},'webhook':{'configured':len(os.getenv('CRON_SECRET',''))>=24}}

    @app.get('/api/workbench',dependencies=[Depends(s.auth)])
    def workbench():
        with s.db() as c:
            return {'tasks':[dict(r) for r in c.execute("SELECT * FROM project_tasks WHERE status='todo' ORDER BY created_at DESC")], 'new_inquiries':[dict(r) for r in c.execute("SELECT id,created_at FROM inquiries WHERE status='new' ORDER BY id DESC")], 'drafts':[draft_dict(r) for r in c.execute('SELECT * FROM quote_drafts WHERE published_version_id IS NULL ORDER BY updated_at DESC')], 'unassigned':c.execute('SELECT COUNT(*) n FROM communications WHERE inquiry_id IS NULL').fetchone()['n']}

    # Local automatic collection. Serverless deployments use the authenticated job/webhook.
    if not os.getenv('VERCEL'):
        import threading
        stop=threading.Event()
        @app.on_event('startup')
        def start_worker():
            from mail_sync import configured
            if not configured() and not ai_client.configuration()['configured']:return
            def worker():
                while not stop.wait(60):
                    try:sync()
                    except Exception:pass
            threading.Thread(target=worker,name='vera-mail-automation',daemon=True).start()
        @app.on_event('shutdown')
        def stop_worker():stop.set()
