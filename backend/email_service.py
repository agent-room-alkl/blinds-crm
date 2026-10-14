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
    return {'configured':ready,'sender':sender if ready else ''},(host,port,mode,sender)

def send_email(recipient,subject,body):
    state,(host,port,mode,sender)=configuration()
    if not state['configured']:raise RuntimeError('Email delivery is not configured')
    address(recipient)
    if '\r' in subject or '\n' in subject:raise ValueError('Invalid email subject')
    message=EmailMessage();message['From']=sender;message['To']=recipient;message['Subject']=subject
    message['Date']=formatdate(localtime=False);message['Message-ID']=make_msgid();message.set_content(body)
    context=ssl.create_default_context()
    transport=smtplib.SMTP_SSL(host,port,timeout=20,context=context) if mode=='ssl' else smtplib.SMTP(host,port,timeout=20)
    with transport as client:
        if mode=='starttls':client.ehlo();client.starttls(context=context);client.ehlo()
        username=os.getenv('SMTP_USERNAME','');password=os.getenv('SMTP_PASSWORD','')
        if username:client.login(username,password)
        if client.send_message(message):raise RuntimeError('Recipient was rejected')
    return message['Message-ID']
