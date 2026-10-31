import copy
import pytest
from mcj import web
from test_security import environment,enroll,post

@pytest.mark.parametrize('prefix',['https://discord.com/api/webhooks/','https://discord.com/api/v10/webhooks/','https://discordapp.com/api/v10/webhooks/'])
def test_discord_accepts_official_versioned_webhooks(prefix):
    from mcj.notify import discord_url
    value=prefix+'123456789/DISPOSABLE_fixture-token'
    assert discord_url(value)==value

@pytest.mark.parametrize('value',[
    'https://discord.com/api/v10/webhooks/123/token/messages/456',
    'https://discord.com/api/v10/webhooks/123/token?wait=true',
    'https://discord.com/api/v10/webhooks/123/token#fragment',
    'https://discord.com.evil.invalid/api/v10/webhooks/123/token',
    'https://discord.com/api/v10/webhooks/not-an-id/token',
    'https://discord.com/api/v10/webhooks/123/',
    'https://discord.com/api/v10/webhooks/123/token%2Fother'
])
def test_discord_rejects_non_webhook_targets(value):
    from mcj.notify import discord_url
    with pytest.raises(ValueError):discord_url(value)

def test_versioned_discord_webhook_can_be_saved_then_tested(environment,monkeypatch):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];sent=[]
    cfg={'enabled':True,'webhook':'https://discord.com/api/v10/webhooks/123456789/DISPOSABLE-fixture','events':['maintenance'],'language':'de'}
    response=post(client,'/api/settings',{'section':'discord','value':cfg},csrf)
    assert response.status_code==200
    monkeypatch.setattr(web,'send_discord',lambda store,*a,**k:sent.append(store.get('discord')['webhook']))
    assert post(client,'/api/settings/discord/test',csrf=csrf).json()=={'ok':True}
    assert sent==[cfg['webhook']]

def test_unconfigured_test_actions_have_clear_codes_without_sending(environment,monkeypatch):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];calls=[]
    monkeypatch.setattr(web,'send_email',lambda *a,**k:calls.append('mail'))
    monkeypatch.setattr(web,'send_discord',lambda *a,**k:calls.append('discord'))
    for path,code in [('smtp','smtp_not_configured'),('discord','discord_disabled')]:
        response=post(client,'/api/settings/'+path+'/test',csrf=csrf)
        assert response.status_code==409 and response.json()['detail']==code
    cfg=app.state.store.get('discord');cfg['enabled']=True;app.state.store.set('discord',cfg,True)
    assert post(client,'/api/settings/discord/test',csrf=csrf).json()['detail']=='discord_webhook_required'
    assert calls==[]

def test_failed_connection_tests_return_codes_without_internal_secrets(environment,monkeypatch):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store
    smtp=st.get('smtp');smtp.update(host='smtp.example.invalid',sender='fixture@example.invalid');st.set('smtp',smtp,True)
    discord=st.get('discord');discord.update(enabled=True,webhook='https://discord.com/api/webhooks/123456789/FIXTURE-ONLY');st.set('discord',discord,True)
    def failure(*a,**k):raise RuntimeError('SENSITIVE-TEST-DETAIL-NEVER-RETURN')
    monkeypatch.setattr(web,'send_email',failure);monkeypatch.setattr(web,'send_discord',failure)
    for path in ('smtp','discord'):
        response=post(client,'/api/settings/'+path+'/test',csrf=csrf)
        assert response.status_code==502 and response.json()['detail']==path+'_test_failed'
        assert 'SENSITIVE' not in response.text
    for path in ('smtp','discord'):
        assert post(client,'/api/settings/'+path+'/test').status_code==403

def test_successful_test_returns_actual_acceptance_and_only_own_email(environment,monkeypatch):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store;sent=[]
    smtp=st.get('smtp');smtp.update(host='smtp.example.invalid',sender='fixture@example.invalid');st.set('smtp',smtp,True)
    discord=st.get('discord');discord.update(enabled=True,webhook='https://discord.com/api/webhooks/123456789/FIXTURE-ONLY');st.set('discord',discord,True)
    def mail(store,recipient,*args):sent.append(recipient);return {'status':'smtp_accepted','delivery':'unconfirmed'}
    monkeypatch.setattr(web,'send_email',mail);monkeypatch.setattr(web,'send_discord',lambda *a,**k:None)
    assert post(client,'/api/settings/smtp/test',csrf=csrf).json()['delivery']=='unconfirmed'
    assert sent==['roman@example.invalid']
    assert post(client,'/api/settings/discord/test',csrf=csrf).json()=={'ok':True}

def test_saved_webhook_reveal_requires_admin_mfa_csrf_and_is_not_in_general_settings(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf'];st=app.state.store
    fixture='https://discord.com/api/webhooks/123456789/DISPOSABLE-FIXTURE'
    cfg=st.get('discord');cfg['webhook']=fixture;st.set('discord',cfg,True)
    assert fixture not in client.get('/api/settings').text
    path='/api/settings/discord/webhook/reveal'
    assert post(client,path).status_code==403
    result=post(client,path,csrf=csrf);assert result.status_code==200 and result.json()=={'webhook':fixture}
    assert result.headers['cache-control']=='no-store'
    with st.db() as db:
        data=db.execute("SELECT data FROM events WHERE event='discord_webhook_viewed'").fetchone()[0]
        assert fixture not in data and 'DISPOSABLE' not in data
        db.execute('UPDATE users SET admin=0 WHERE id=1')
    assert post(client,path,csrf=csrf).status_code==403
