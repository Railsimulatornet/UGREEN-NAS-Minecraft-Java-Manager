import base64,xml.etree.ElementTree as ET
from urllib.parse import urlparse,parse_qs
from test_security import environment,enroll,post

def test_enrollment_provides_local_qr_for_exact_totp_uri_with_no_remote_resources(environment):
    app,client,_,_=environment;csrf=enroll(environment)['csrf']
    response=post(client,'/api/auth/setup/totp',csrf=csrf)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    value=response.json();assert value['qr'].startswith('data:image/svg+xml;base64,')
    svg=base64.b64decode(value['qr'].split(',',1)[1],validate=True)
    tree=ET.fromstring(svg)
    assert tree.tag=='{http://www.w3.org/2000/svg}svg'
    assert tree.find('{http://www.w3.org/2000/svg}path') is not None
    assert b'<script' not in svg and b'href=' not in svg and value['secret'].encode() not in svg
    uri=urlparse(value['uri']);assert uri.scheme=='otpauth' and uri.netloc=='totp'
    assert parse_qs(uri.query)['secret']==[value['secret']]
    assert parse_qs(uri.query)['issuer']==['MCJ Manager']
    with app.state.store.db() as db:
        events=' '.join(row[0] for row in db.execute('SELECT data FROM events'))
        challenge=db.execute("SELECT data FROM challenges WHERE kind='enroll_totp' ORDER BY expires DESC LIMIT 1").fetchone()[0]
    assert value['secret'] not in events and value['qr'] not in events
    assert value['secret'] not in challenge
    assert post(client,'/api/auth/setup/totp').status_code==403
