"""Server-only SMTP transport. No credentials returned to the client."""
import os,re,smtplib,ssl
from email.message import EmailMessage
from email.utils import formatdate,make_msgid

def address(value):
    if not re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+',value):raise ValueError('Enter a valid email address')
    return value

def configuration():
    host=os.getenv('SMTP_HOST','').strip();sender=os.getenv('SMTP_FROM','').strip()
    mode=os.getenv('SMTP_SECURITY','starttls')
    try:port=int(os.getenv('SMTP_PORT','465' if mode=='ssl' else '587'))
    except ValueError:port=0
    ready=bool(host and sender and mode in ('starttls','ssl') and 0<port<65536)
    try:address(sender)
    except ValueError:ready=False
    delivery_mode=os.getenv('VERA_EMAIL_MODE','demo').strip().lower()
    if delivery_mode not in ('demo','live','disabled'):delivery_mode='disabled'
    sandbox=os.getenv('VERA_DEMO_EMAIL_ADDRESS','').strip()
    try:address(sandbox)
    except ValueError:sandbox=''
    if delivery_mode=='demo':
        ready=ready and bool(sandbox) and sender.casefold()==sandbox.casefold()
        sender=sandbox
    elif delivery_mode!='live':ready=False
    return {'configured':ready,'sender':sender if ready else '',
            'mode':delivery_mode,'delivery_enabled':ready,'demo_recipient':sandbox},(host,port,mode,sender)

def send_email(recipient,subject,body,attachments=()):
    state,(host,port,mode,sender)=configuration()
    if not state['configured']:raise RuntimeError('Email delivery is not configured')
    if state['mode']=='demo':
        recipient=state['demo_recipient']
        sender=recipient
    elif state['mode']!='live':raise RuntimeError('Email delivery is disabled')
    address(recipient)
    if '\r' in subject or '\n' in subject:raise ValueError('Invalid email subject')
    message=EmailMessage();message['From']=sender;message['To']=recipient;message['Subject']=subject
    message['Date']=formatdate(localtime=False);message['Message-ID']=make_msgid();message.set_content(body)
    for name,data,maintype,subtype in attachments:
        message.add_attachment(data,maintype=maintype,subtype=subtype,filename=name)
    context=ssl.create_default_context()
    transport=smtplib.SMTP_SSL(host,port,timeout=20,context=context) if mode=='ssl' else smtplib.SMTP(host,port,timeout=20)
    with transport as client:
        if mode=='starttls':client.ehlo();client.starttls(context=context);client.ehlo()
        username=os.getenv('SMTP_USERNAME','');password=os.getenv('SMTP_PASSWORD','')
        if username:client.login(username,password)
        if client.send_message(message):raise RuntimeError('Recipient was rejected')
    return message['Message-ID']
