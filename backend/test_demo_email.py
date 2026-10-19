"""Demo mail is self-only; missing/mismatched sandbox settings never open SMTP."""
import os
from unittest.mock import patch
from email_service import configuration, send_email

with patch.dict(os.environ,{'VERA_EMAIL_MODE':'demo','SMTP_HOST':'smtp.example.invalid','SMTP_FROM':'demo@example.invalid','VERA_DEMO_EMAIL_ADDRESS':''}):
    state,_=configuration()
    assert state['mode']=='demo' and not state['configured'] and not state['delivery_enabled']
    with patch('email_service.smtplib.SMTP') as smtp, patch('email_service.smtplib.SMTP_SSL') as secure:
        try:
            send_email('customer@example.invalid','Demo invoice','Never deliver')
            raise AssertionError('Demo delivery must be refused')
        except RuntimeError as err:
            assert 'not configured' in str(err)
        smtp.assert_not_called()
        secure.assert_not_called()
with patch.dict(os.environ,{},clear=True):
    assert configuration()[0]['mode']=='demo'
for security in ('starttls','ssl'):
    env={'VERA_EMAIL_MODE':'demo','VERA_DEMO_EMAIL_ADDRESS':'owner@example.invalid','SMTP_FROM':'owner@example.invalid','SMTP_HOST':'smtp.example.invalid','SMTP_SECURITY':security}
    with patch.dict(os.environ,env),patch('email_service.smtplib.SMTP') as smtp,patch('email_service.smtplib.SMTP_SSL') as secure:
        transport=secure if security=='ssl' else smtp
        client=transport.return_value.__enter__.return_value
        client.send_message.return_value={}
        send_email('customer@example.invalid','Demo invoice','Test body')
        message=client.send_message.call_args.args[0]
        assert message['From']=='owner@example.invalid' and message['To']=='owner@example.invalid'
        assert message.get('Cc') is None and message.get('Bcc') is None
        assert 'customer@example.invalid' not in str(message)
    with patch.dict(os.environ,{**env,'SMTP_FROM':'different@example.invalid'}):
        assert not configuration()[0]['configured']
print('PASS demo defaults blocked; configured STARTTLS/SSL force identical sandbox From/To; mismatched sender refused')
