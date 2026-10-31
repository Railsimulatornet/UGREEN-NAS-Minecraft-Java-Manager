import email.message
import smtplib
import ssl
import httpx
import json
import re
import socket
from urllib.parse import urlparse


class MailDeliveryError(RuntimeError):
    def __init__(self, code):
        self.code=code
        super().__init__(code)


def send_email(store,recipient,subject,body,actor=None,*,configuration=None):
    cfg=configuration if configuration is not None else store.get('smtp')
    if '\r' in recipient or '\n' in recipient or '\n' in subject or '\r' in subject:
        raise ValueError('Invalid mail header')
    message=email.message.EmailMessage()
    message['From']=cfg['sender'];message['To']=recipient;message['Subject']=subject
    message.set_content(body)
    context=ssl.create_default_context()
    try:
        if cfg['security']=='tls':
            conn=smtplib.SMTP_SSL(cfg['host'],cfg['port'],timeout=15,context=context)
        elif cfg['security']=='starttls':
            conn=smtplib.SMTP(cfg['host'],cfg['port'],timeout=15)
            conn.ehlo();conn.starttls(context=context)
        else:raise ValueError('Encrypted SMTP required')
        with conn:
            conn.ehlo()
            if cfg['username']:conn.login(cfg['username'],cfg['password'])
            refused=conn.send_message(message)
            if refused:raise RuntimeError('Recipient rejected')
        store.event('email','smtp_accepted',actor,{'recipient':recipient,'subject':subject})
        return {'status':'smtp_accepted','delivery':'unconfirmed'}
    except Exception as exc:
        store.event('email','send_failed',actor,{'recipient':recipient,'error_class':type(exc).__name__})
        if isinstance(exc,smtplib.SMTPAuthenticationError):code='smtp_authentication_failed'
        elif isinstance(exc,(ssl.SSLError,smtplib.SMTPNotSupportedError)):code='smtp_secure_connection_failed'
        elif isinstance(exc,(smtplib.SMTPRecipientsRefused,smtplib.SMTPSenderRefused)):code='smtp_address_rejected'
        elif isinstance(exc,(socket.gaierror,TimeoutError,ConnectionError,OSError)):code='smtp_connection_failed'
        else:code='email_setup_delivery_failed'
        raise MailDeliveryError(code) from None


def discord_url(value):
    u=urlparse(value)
    if u.scheme!='https' or u.hostname not in {'discord.com','discordapp.com'} or u.port not in {None,443}:
        raise ValueError('Official HTTPS Discord webhook required')
    if u.username or u.password or u.query or u.fragment or not re.fullmatch(r'/api/(?:v[0-9]{1,2}/)?webhooks/[0-9]+/[A-Za-z0-9_-]+',u.path):
        raise ValueError('Invalid webhook URL')
    return value


def send_discord(store,text,status=False,actor=None):
    cfg=store.get('discord')
    if not cfg.get('enabled'):raise ValueError('Discord disabled')
    url=discord_url(cfg['webhook'])
    payload={'content':text[:1900],'allowed_mentions':{'parse':[]}}
    message_id=cfg.get('status_message_id') if status else None
    try:
        with httpx.Client(timeout=12,follow_redirects=False) as client:
            if message_id:
                if not str(message_id).isdigit():raise ValueError('Invalid status message id')
                response=client.patch(url+'/messages/'+str(message_id),json=payload)
                if response.status_code==404:
                    message_id=None
                    response=client.post(url+'?wait=true',json=payload)
            else:response=client.post(url+'?wait=true',json=payload)
            response.raise_for_status()
            if status and not message_id:
                identifier=response.json()['id']
                if not str(identifier).isdigit():raise ValueError('Invalid status message id')
                with store.db(immediate=True) as db:
                    current=db.execute("SELECT value FROM settings WHERE name='discord'").fetchone()
                    latest=json.loads(store.open(current['value']))
                    if latest.get('webhook')==cfg['webhook']:
                        latest['status_message_id']=identifier
                        db.execute("UPDATE settings SET value=? WHERE name='discord'",(store.seal(json.dumps(latest)),))
        store.event('discord','status_updated' if status else 'sent',actor)
    except Exception as exc:
        store.event('discord','failed',actor,{'error_class':type(exc).__name__})
        raise RuntimeError('Discord request failed') from None
