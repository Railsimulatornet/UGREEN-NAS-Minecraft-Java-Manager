"""Check the reviewed DE/EN contract, not gameplay or installation acceptance."""
import ast
import hashlib
import json
from pathlib import Path
import re

import pytest

from mcj import dispatch
from test_security import environment,enroll,post

ROOT=Path(__file__).parents[1]


def catalogue():
    source=(ROOT/'mcj/static/i18n.js').read_text(encoding='utf-8')
    return json.loads(source[source.index('{'):source.rindex('}')+1])


def test_all_literal_auth_and_web_errors_have_human_de_en_messages():
    words=catalogue()
    for name in ('auth','email_setup','web'):
        tree=ast.parse((ROOT/'mcj'/f'{name}.py').read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node,ast.Call) or not node.args:continue
            function=node.func
            if not ((isinstance(function,ast.Name) and function.id=='error') or (isinstance(function,ast.Attribute) and function.attr=='error')):continue
            if isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str):
                for lang in ('de','en'):assert words[lang].get(node.args[0].value),(name,lang,node.args[0].value)


def test_readme_guides_and_ui_agree_on_email_first_choice():
    readme=(ROOT/'README.md').read_text(encoding='utf-8')
    words=catalogue()
    for lang in ('DE','EN'):
        text=(ROOT/f'docs/INSTALLATION-{lang}.md').read_text(encoding='utf-8')
        locale=lang.lower()
        for key in ('emailFactor','totp','emailSetupTitle','emailSetupHost','emailSetupSender','emailSetupSend','verify','useRecovery','backupCodes'):
            assert '**'+words[locale][key]+'**' in text,(lang,key)
        assert '**10 Minuten**' in text if lang=='DE' else '**10 minutes**' in text
        assert 'STARTTLS' in text and 'TLS' in text
        assert '/blob/main/' in text
        assert '/blob/nachbesserung-' not in text
        for path in re.findall(r'!\[[^]]*\]\(([^)]+)\)',text):assert (ROOT/'docs'/path).is_file(),path
    assert 'Browser und Authenticator-App auf deinem Smartphone.' not in readme
    assert 'A browser and an authenticator app on your phone.' not in readme
    assert 'E-Mail-Sicherheitscode' in readme and 'Email security code' in readme


def test_user_documentation_and_version_info_contain_no_internal_release_notes():
    words=catalogue()
    sources=[(ROOT/path).read_text(encoding='utf-8') for path in (
        'README.md','docs/INSTALLATION-DE.md','docs/INSTALLATION-EN.md','docs/AKTUALISIEREN.md')]
    sources.extend(words[lang]['noPublicRelease'] for lang in ('de','en'))
    forbidden=(r'private review (?:branch|build)',r'privat\w* Prüf(?:branch|stand)',
        r'öffentliche Installation (?:noch )?nicht freigegeben',r'public installation is not approved',
        r'authorised (?:registry )?access',r'freigeschalteter Zugriff',r'Image bleibt privat',
        r'(?:repository|image) (?:and (?:image|repository) )?remain(?:s)? private')
    for source in sources:
        for pattern in forbidden:assert not re.search(pattern,source,re.I),pattern


def test_manual_sources_have_parallel_sections_and_no_private_lan_or_credentials():
    guides=[(ROOT/f'docs/INSTALLATION-{lang}.md').read_text(encoding='utf-8') for lang in ('DE','EN')]
    numbers=lambda source:re.findall(r'^## ([0-9.]+) ',source,re.M)
    assert numbers(guides[0])==numbers(guides[1])
    for source in [*guides,(ROOT/'README.md').read_text(encoding='utf-8')]:
        assert '192.168.120.' not in source
        assert not any(value in source for value in ('worktest@','WORKTest,','\ufffd'))


@pytest.mark.parametrize('language',['de','en'])
def test_event_display_is_localized_without_exposing_internal_keys_by_default(environment,language):
    app,client,_,_=environment;csrf=enroll(environment)['csrf']
    post(client,'/api/auth/language',{'language':language},csrf)
    app.state.store.event('auth','factor_failed',1)
    app.state.store.event('system','unfamiliar_internal_error_key',data={'detail':'PRIVATE-RAW-ERROR'})
    response=client.get('/api/events')
    assert response.status_code==200
    for event in response.json():
        assert event['title'] and event['description']
        assert 'unfamiliar_internal_error_key' not in event['title']+event['description']
        assert 'PRIVATE-RAW-ERROR' not in event['title']+event['description']
        assert ('Öffne' if language=='de' else 'Open') in event['description'] or event['event']!='unfamiliar_internal_error_key'
    item=next(x for x in response.json() if x['event']=='factor_failed')
    assert ('E-Mail-Code' if language=='de' else 'email code') in item['description']


@pytest.mark.parametrize('language',['de','en'])
@pytest.mark.parametrize('channel',['email','discord'])
def test_unknown_notification_is_readable_without_reflecting_a_raw_error_key(language,channel):
    event={'id':1,'at':1793473200,'category':'system','event':'unfamiliar_internal_error_key','data':json.dumps({'password':'PRIVATE-SECRET'})}
    title,body=dispatch.render([event],language,'https://manager.example.test',channel=channel)
    assert 'unfamiliar_internal_error_key' not in title+body and 'PRIVATE-SECRET' not in title+body
    assert ('Ereignisse' if language=='de' else 'Events') in body


def test_pdf_manuals_match_the_reviewed_sources_and_only_two_current_outputs():
    proof=json.loads((ROOT/'docs/handbooks.json').read_text())
    for lang in ('DE','EN'):
        item=proof['languages'][lang]
        for kind,rel in [('source',f'docs/INSTALLATION-{lang}.md'),('pdf',f'docs/Installation-{lang}.pdf')]:
            assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==item[kind+'_sha256']
    assert sorted(p.name for p in (ROOT/'docs').glob('*.pdf'))==['Installation-DE.pdf','Installation-EN.pdf']
