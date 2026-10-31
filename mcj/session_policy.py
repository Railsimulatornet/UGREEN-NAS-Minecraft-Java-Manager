"""Per-administrator preferences, frozen into each newly authenticated session."""
from pydantic import BaseModel, Field, StrictInt, model_validator

DEFAULT={'absolute_seconds':43200,'idle_seconds':14400}


class Policy(BaseModel):
    model_config={'extra':'forbid'}
    absolute_hours:StrictInt=Field(ge=1,le=168)
    idle_minutes:StrictInt=Field(ge=15,le=1440)

    @model_validator(mode='after')
    def ordered(self):
        if self.idle_minutes>self.absolute_hours*60:raise ValueError('idle_exceeds_session')
        return self

    def seconds(self):return {'absolute_seconds':self.absolute_hours*3600,'idle_seconds':self.idle_minutes*60}


def preference(st,user_id,admin):
    if not admin:return dict(DEFAULT)
    value=st.get('admin_session_policy:'+str(user_id))
    if not isinstance(value,dict):return dict(DEFAULT)
    try:
        absolute=value['absolute_seconds'];idle=value['idle_seconds']
        if type(absolute) is not int or type(idle) is not int or absolute%3600 or idle%60:raise ValueError()
        return Policy(absolute_hours=absolute//3600,idle_minutes=idle//60).seconds()
    except (ValueError,KeyError,TypeError):return dict(DEFAULT)


def view(session):
    return {'created':session['session_created'],'absolute_expires':min(session['expires'],session['session_created']+session['absolute_seconds']),
            'idle_expires':session['last_seen']+session['idle_seconds'],'absolute_seconds':session['absolute_seconds'],'idle_seconds':session['idle_seconds'],
            'remember_days':session.get('remember_days',0) if isinstance(session,dict) else session['remember_days']}
