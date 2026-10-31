"""Password-authenticated, session-bound email enrollment, including first SMTP setup."""
import hmac
import json
import secrets
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from .notify import MailDeliveryError


class MailSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    host: str = Field(min_length=1, max_length=253, pattern=r'^[A-Za-z0-9.-]+$')
    port: StrictInt = Field(ge=1, le=65535)
    security: Literal['tls', 'starttls']
    username: str = Field(min_length=1, max_length=254)
    sender: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@\r\n]+@[^\s@\r\n]+$')
    password: str = Field(min_length=1, max_length=1000, repr=False)

    @field_validator('username')
    @classmethod
    def single_line(cls, value):
        if any(char in value for char in '\r\n\x00'):
            raise ValueError('invalid_smtp_username')
        return value


def configured(settings):
    return bool(settings.get('host') and settings.get('sender'))


def fingerprint(st, settings):
    return st.digest(json.dumps(settings, sort_keys=True, separators=(',', ':')))


def can_configure(user, settings):
    # Existing MFA users use Settings, never this password-only first-start route.
    return bool(user['admin'] and not user['factor'] and not configured(settings))


def start(st, user, binding, send, settings=None):
    from .auth import error
    current = st.get('smtp')
    if settings is not None and not can_configure(user, current):
        error('email_setup_settings_unavailable', 409)
    if settings is None and not configured(current):
        error('smtp_not_configured', 409)
    if not st.rate('enroll-email:' + str(user['id']), 3, 600):
        error('rate_limited', 429)
    token = secrets.token_urlsafe(32)
    code = str(secrets.randbelow(1000000)).zfill(6)
    context = {'binding': binding, 'generation': user['generation'],
               'email': st.digest(user['email'].casefold()),
               'smtp_before': fingerprint(st, current), 'settings': settings}
    with st.db(immediate=True) as db:
        # A replacement attempt invalidates older codes from this session only.
        for row in db.execute("SELECT token,data FROM challenges WHERE user_id=? AND kind='enroll_email'", (user['id'],)).fetchall():
            try:
                previous = json.loads(st.open(row['data']))
            except Exception:
                continue
            if previous.get('binding') == binding:
                db.execute('DELETE FROM challenges WHERE token=?', (row['token'],))
        db.execute('INSERT INTO challenges(token,user_id,kind,expires,code,data) VALUES(?,?,?,?,?,?)',
                   (st.digest(token), user['id'], 'enroll_email', time.time() + 600,
                    st.digest(token + ':' + code), st.seal(json.dumps(context))))
    de = user['language'] == 'de'
    subject = 'MCJ Manager – ' + ('E-Mail-Anmeldung bestätigen' if de else 'Confirm email sign-in')
    body = (f'Dein Sicherheitscode: {code}\n\nGib diesen Code im MCJ Manager ein, um den Empfang an deiner Konto-Adresse zu bestätigen. '
            'Er gilt einmalig für 10 Minuten. Erst danach wird die E-Mail-Anmeldung eingerichtet.\n\n'
            'Wenn du die Einrichtung nicht begonnen hast, gib den Code nicht weiter.\n') if de else (
            f'Your security code: {code}\n\nEnter this code in MCJ Manager to confirm receipt at your account email address. '
            'It works once and expires in 10 minutes. Email sign-in is set up only after you confirm it.\n\n'
            'If you did not start setup, do not share the code.\n')
    try:
        # Wait for SMTP acceptance. Entering the received code proves inbox access.
        if settings is None:
            send(st, user['email'], subject, body, user['id'])
        else:
            send(st, user['email'], subject, body, user['id'], configuration=settings)
    except Exception as exc:
        with st.db() as db:
            db.execute('DELETE FROM challenges WHERE token=?', (st.digest(token),))
        error(exc.code if isinstance(exc, MailDeliveryError) else 'email_setup_delivery_failed', 502)
    return {'challenge': token}


def confirm(st, user, binding, token, code):
    """Confirm receipt and install the factor and optional SMTP settings atomically."""
    good = False
    now = time.time()
    with st.db(immediate=True) as db:
        row = db.execute("SELECT * FROM challenges WHERE token=? AND user_id=? AND kind='enroll_email'",
                         (st.digest(token), user['id'])).fetchone()
        current = db.execute('SELECT * FROM users WHERE id=? AND enabled=1', (user['id'],)).fetchone()
        smtp_row = db.execute("SELECT * FROM settings WHERE name='smtp'").fetchone()
        smtp = json.loads(st.open(smtp_row['value']))
        try:
            context = json.loads(st.open(row['data'])) if row else {}
        except Exception:
            context = {}
        valid = (row and current and row['expires'] > now and row['attempts'] < 5
                 and context.get('binding') == binding
                 and context.get('generation') == current['generation']
                 and context.get('email') == st.digest(current['email'].casefold())
                 and context.get('smtp_before') == fingerprint(st, smtp))
        if valid and context.get('settings') is not None:
            valid = can_configure(current, smtp)
        if valid:
            db.execute('UPDATE challenges SET attempts=attempts+1 WHERE token=?', (row['token'],))
            good = hmac.compare_digest(row['code'] or '', st.digest(token + ':' + code))
            if good:
                if context.get('settings') is not None:
                    db.execute("UPDATE settings SET value=?,secret=1 WHERE name='smtp'",
                               (st.seal(json.dumps(context['settings'])),))
                db.execute("UPDATE users SET factor='email',totp=NULL,totp_last=-1,generation=generation+1 WHERE id=?", (user['id'],))
                db.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
                db.execute('DELETE FROM challenges WHERE user_id=?', (user['id'],))
    return good
