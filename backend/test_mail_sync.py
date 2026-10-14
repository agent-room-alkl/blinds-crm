"""IMAP checkpoint/replay and PEEK behavior, entirely mocked."""
import os,tempfile,json,sqlite3
from contextlib import contextmanager
from unittest.mock import patch,MagicMock
from workflow_schema import migrate
from workflow import Inbound
from mail_sync import collect,parse_message
raw=b'From: Buyer <buyer@example.invalid>\r\nTo: sales@example.invalid\r\nMessage-ID: <imap-test@example.invalid>\r\nIn-Reply-To: <sent@example.invalid>\r\nSubject: Reply\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nConfirm width 1200 mm.'
assert parse_message(raw)['references']==['<sent@example.invalid>']
html=raw.replace(b'text/plain',b'text/html').replace(b'Confirm width 1200 mm.',b'<p>Visible</p><script>hidden</script>')
assert 'Visible' in parse_message(html)['body'] and 'hidden' not in parse_message(html)['body']
with tempfile.TemporaryDirectory() as folder:
    @contextmanager
    def db():
        c=sqlite3.connect(folder+'/test.db');c.row_factory=sqlite3.Row
        try:
            with c:yield c
        finally:c.close()
    with db() as c:migrate(c)
    client=MagicMock();client.__enter__.return_value=client;client.select.return_value=('OK',[]);client.response.return_value=('UIDVALIDITY',[b'1'])
    def uid(command,*args):return ('OK',[b'1 2 3']) if command=='search' else ('OK',[(b'fetch',raw)])
    client.uid.side_effect=uid
    messages=[]
    env={'IMAP_HOST':'imap.example.invalid','IMAP_USERNAME':'test','IMAP_PASSWORD':'test-only'}
    with patch.dict(os.environ,env),patch('mail_sync.imaplib.IMAP4_SSL',return_value=client):
        assert collect(db,json.dumps,messages.append,Inbound)==3
        client.select.assert_called_with('INBOX',readonly=True)
        assert all(call.args[-1]=='(BODY.PEEK[])' for call in client.uid.call_args_list if call.args[0]=='fetch')
        assert collect(db,json.dumps,messages.append,Inbound)==0
        def failure(_):raise RuntimeError('archive unavailable')
        client.response.return_value=('UIDVALIDITY',[b'2'])
        assert collect(db,json.dumps,failure,Inbound)==0
        assert collect(db,json.dumps,messages.append,Inbound)==3
    print('PASS: IMAP read-only/PEEK, UID checkpoint replay, mailbox reset, archive failure retry and safe HTML text extraction; no real mailbox accessed')
