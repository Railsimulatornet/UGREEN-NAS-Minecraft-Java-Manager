import re

import pyotp
import pytest
from fastapi.testclient import TestClient

from test_security import environment, enroll, post, configure_mail


@pytest.mark.parametrize('old_method,new_method', [('email', 'totp'), ('totp', 'email')])
def test_factor_change_keeps_existing_method_until_confirmed_and_replaces_sessions_and_codes(environment, old_method, new_method):
    app, client, credentials, mail = environment
    initial = enroll(environment, method=old_method)
    if new_method=='email':configure_mail(environment)
    st = app.state.store
    other = TestClient(app, base_url='https://testserver')
    other.cookies.update(client.cookies)
    with st.db() as db:
        before = dict(db.execute('SELECT * FROM users WHERE id=1').fetchone())
        before_sessions = [tuple(row) for row in db.execute('SELECT token,mfa,generation,created,expires FROM sessions')]

    setup = post(client, '/api/auth/setup/' + new_method, csrf=initial['csrf'])
    assert setup.status_code == 200
    setup = setup.json()
    code = (pyotp.TOTP(setup['secret']).now() if new_method == 'totp'
            else re.search(r'\b\d{6}\b', mail[-1]['body'])[0])
    payload = {'method': new_method, 'challenge': setup['challenge'], 'code': code}
    # Opening the picker, abandoning setup, or entering a wrong code cannot replace the active method.
    failed = post(client, '/api/auth/setup/confirm', {**payload, 'code': 'wrong-code'}, initial['csrf'])
    assert failed.status_code == 401
    with st.db() as db:
        after_failure = dict(db.execute('SELECT * FROM users WHERE id=1').fetchone())
        assert all(after_failure[key] == before[key] for key in ['factor', 'totp', 'totp_last', 'generation'])
        assert [tuple(row) for row in db.execute('SELECT token,mfa,generation,created,expires FROM sessions')] == before_sessions
    assert other.get('/api/auth/me').json()['user']['factor'] == old_method

    changed = post(client, '/api/auth/setup/confirm', payload, initial['csrf'])
    assert changed.status_code == 200
    result = changed.json()
    assert len(result['backup_codes']) == 10 and result['csrf'] != initial['csrf']
    current = client.get('/api/auth/me')
    assert current.status_code == 200 and current.json()['mfa_verified']
    assert current.json()['user']['factor'] == new_method
    assert other.get('/api/auth/me').status_code == 401
    with st.db() as db:
        after = dict(db.execute('SELECT * FROM users WHERE id=1').fetchone())
        assert after['generation'] == before['generation'] + 1
        assert bool(after['totp']) == (new_method == 'totp')
        assert db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=1').fetchone()[0] == 1
    assert not st.consume_recovery(1, initial['backup_codes'][0])
    assert st.consume_recovery(1, result['backup_codes'][0])
    assert not st.consume_recovery(1, result['backup_codes'][0])


def test_existing_factor_cannot_be_changed_from_password_only_session(environment):
    app, client, credentials, mail = environment
    initial = enroll(environment, method='email')
    assert post(client, '/api/auth/logout', csrf=initial['csrf']).status_code == 200
    pending = post(client, '/api/auth/login', {'username': 'Roman', 'password': 'A-Strong-Test-Password-2026!'})
    assert pending.status_code == 200
    csrf = pending.json()['csrf']
    for method in ['totp', 'email']:
        assert post(client, '/api/auth/setup/' + method, csrf=csrf).status_code == 403
    assert post(client, '/api/auth/setup/confirm', {'method': 'totp', 'challenge': 'unused', 'code': '123456'}, csrf).status_code == 403
    assert client.get('/api/auth/me').json()['user']['factor'] == 'email'
