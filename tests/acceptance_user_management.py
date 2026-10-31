"""Admin edit, session revocation and assisted MFA recovery against the live clone."""
name='web_user_edit_disable_and_admin_assisted_factor_recovery'
roman=enroll('Roman','totp');roman.reauthenticate();viewer=enroll('AcceptanceViewer','totp')
users=roman.get('/users');target=next(x for x in users if x['username']=='AcceptanceViewer');owner=next(x for x in users if x['username']=='Roman')
data={key:target[key] for key in ['username','email','admin','language','enabled']}
viewer.post('/users/'+str(target['id']),data,403)
viewer.post('/users/'+str(owner['id'])+'/recovery',{},403)
roman.post('/users/'+str(owner['id'])+'/recovery',{},409)
changed=roman.post('/users/'+str(target['id']),{**data,'language':'en'})
assert changed['sessions_invalidated'];viewer.get('/auth/me',401)
viewer=enroll('AcceptanceViewer','totp')
previous=mail_fingerprint();requested=roman.post('/users/'+str(target['id'])+'/recovery')
assert requested['factor_changed'] is False
message=mail_message(previous)
assert message['recipient']==target['email']
token=re.search(r'#recover=([A-Za-z0-9_-]+)',message['body'])[1]
assert viewer.get('/auth/me')['user']['factor']=='totp'
anonymous=BrowserClient('RecoveryAnonymous')
anonymous.post('/auth/recovery/complete',{'token':token,'password':'Deliberately-Wrong-Password'},401)
assert viewer.get('/auth/me')['user']['factor']=='totp'
password=fixture['accounts']['AcceptanceViewer']['password']
completed=anonymous.post('/auth/recovery/complete',{'token':token,'password':password})
assert completed['password_change_required'] and completed['factor_setup_required']
anonymous.post('/auth/recovery/complete',{'token':token,'password':password},401)
viewer.get('/auth/me',401)
viewer.login();viewer.get('/overview',403)
fixture['accounts']['AcceptanceViewer']['new_password']=secrets.token_urlsafe(24)+'Aa1!';save()
viewer=enroll('AcceptanceViewer','totp');assert viewer.get('/auth/me')['mfa_verified']
disabled=roman.post('/users/'+str(target['id']),{**data,'enabled':False})
assert disabled['sessions_invalidated'];viewer.get('/auth/me',401)
roman.post('/users/'+str(target['id']),data)
viewer=enroll('AcceptanceViewer','totp')
assert viewer.get('/auth/me')['mfa_verified']
assert token not in json.dumps(roman.get('/events')) and token not in roman.client.get('/api/diagnostics',headers={'Cookie':'__Host-mcj='+roman.cookie}).text
image=__import__('mcj.controller',fromlist=['client']).client.containers.get('mcj_acceptance_manager').attrs['Image']
fixture.setdefault('coverage',{})[name]={'image_id':image,'checked_at':time.time()}
report(name,{'scope':'acceptance_only','viewer_privileged_writes_denied':True,'edit_and_disable_revoke_sessions':True,
    'recovery_requires_other_admin_email_link_and_original_password':True,'wrong_password_rejected':True,'token_single_use':True,
    'application_access_denied_until_password_change_and_new_factor':True,'reenrollment_and_reenable':'passed',
    'recovery_token_not_in_events_or_diagnostics':True,'production_accounts_changed':False,'image_id':image})
