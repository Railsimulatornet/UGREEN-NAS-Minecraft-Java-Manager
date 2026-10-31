"""Disposable acceptance server; this file is not copied into the production image."""
import json
import os
from pathlib import Path
import threading
import sys
sys.path.insert(0, '/opt/mcj')
import uvicorn
from mcj import auth,notify
from mcj.web import create_app

app=create_app()
mail_lock=threading.Lock()
def capture_mail(store,recipient,subject,body,actor=None):
    # Only the disposable test process replaces delivery. Tokens remain encrypted on disk.
    with mail_lock:
        store.atomic(store.state/'.acceptance-mail.fernet',store.cipher.encrypt(json.dumps({
            'recipient':recipient,'subject':subject,'body':body}).encode()),0o600)
    store.event('email','acceptance_mail_captured',actor)
    return {'status':'accepted_by_test_transport','delivery':'test_capture'}
auth.send_email=capture_mail
notify.send_email=capture_mail
def capture_discord(store,text,status=False,actor=None):
    store.atomic(store.state/'.acceptance-discord.fernet',store.cipher.encrypt(json.dumps({'text':text,'status':status}).encode()),0o600)
    store.event('discord','acceptance_discord_captured',actor)
    return {'status':'accepted_by_test_transport'}
notify.send_discord=capture_discord
uvicorn.run(app,host='0.0.0.0',port=8090,access_log=False,proxy_headers=False)
