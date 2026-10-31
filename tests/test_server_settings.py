import pytest
from mcj.server_settings import normalize

def test_properties_keep_guard_and_network_boundaries():
    current={'version':'26.3','memory_mb':3072,'properties':{'motd':'Bisher','pvp':'false','level-name':'world'}}
    changed=normalize(current,{'properties':{'motd':'Grüße an alle!','pvp':True,'level-name':'zweite_welt'}})
    assert changed['properties']['motd']=='Grüße an alle!' and changed['properties']['pvp']=='true'
    assert changed['world']=='zweite_welt' and changed['properties']['online-mode']=='true'
    assert changed['properties']['gamemode']=='spectator' and changed['properties']['pause-when-empty-seconds']=='0'
    assert current['properties']['motd']=='Bisher'

@pytest.mark.parametrize('key,value',[
 ('online-mode','false'),('gamemode','survival'),('server-port','25575'),
 ('rcon.password','secret'),('management-server-secret','secret'),('management-server-tls-keystore-password','secret'),('management-server-enabled','true'),
 ('pause-when-empty-seconds','60'),('level-name','../outside'),('motd','first\nsecond'),
])
def test_unsafe_property_change_is_rejected(key,value):
    with pytest.raises(ValueError):normalize({'version':'26.3'},{'properties':{key:value}})

def test_minecraft_properties_roundtrip_preserves_unicode_and_escaped_punctuation():
    from mcj.properties import loads,dumps
    text='motd=Grüße aus der Abnahme\\!\nname\\ with\\ spaces :  leading\\ value\nlong=first\\\n  second\nemoji=\\uD83D\\uDE0A\n'
    parsed=loads(text)
    assert parsed=={'motd':'Grüße aus der Abnahme!','name with spaces':'leading value','long':'firstsecond','emoji':'😊'}
    assert loads(dumps(parsed))==parsed
