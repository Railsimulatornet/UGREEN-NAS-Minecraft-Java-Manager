"""Own administrator UI preferences; never game configuration or credentials."""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .server_settings import SECRET_KEYS
import re

class Preferences(BaseModel):
    model_config=ConfigDict(extra='forbid')
    favorite_properties:list[str]=Field(default_factory=list,max_length=64)

    @field_validator('favorite_properties')
    @classmethod
    def validate_keys(cls,values):
        if any(not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',key) or key in SECRET_KEYS for key in values):
            raise ValueError('invalid_favorite_property')
        return sorted(set(values))

def own(st,user_id):
    value=st.get('admin_ui_preferences:'+str(user_id))
    try:return Preferences.model_validate(value or {}).model_dump()
    except (ValueError,TypeError):return Preferences().model_dump()
