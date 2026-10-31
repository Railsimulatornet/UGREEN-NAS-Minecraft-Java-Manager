"""Authentication mail must identify the requested action and retain one-time code handling."""
import re
import pytest
from fastapi import BackgroundTasks
from mcj import auth
from test_dispatch import store


@pytest.mark.parametrize('language',['de','en'])
@pytest.mark.parametrize('kind',['login','reauth','enroll_email','reset_factor'])
def test_security_mail_identifies_purpose_and_code_is_still_single_use(store,language,kind):
    with store.db() as db:user=dict(db.execute('SELECT * FROM users ORDER BY id LIMIT 1').fetchone())
    user['language']=language
    background=BackgroundTasks()
    token=auth.issue_email(store,user,kind,background)
    assert len(background.tasks)==1
    args=background.tasks[0].args
    subject,body=args[2:4]
    assert subject.startswith('MCJ Manager – Code: ')
    assert ('Wofür:' if language=='de' else 'Purpose:') in body
    assert ('nicht weiter' if language=='de' else 'do not share') in body
    code=re.search(r'\b\d{6}\b',body)[0]
    assert auth.consume_email(store,user['id'],token,code,kind)
    assert not auth.consume_email(store,user['id'],token,code,kind)
