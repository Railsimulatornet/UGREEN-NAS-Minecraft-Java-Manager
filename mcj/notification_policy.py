"""Recipient authority is independent of a personal category preference."""
import json

SHARED={'server','mods','backup','maintenance','system','player'}
TARGET_EVENTS={'user_created','user_updated','factor_recovery_requested',
               'factor_recovery_delivery_failed','factor_recovery_completed'}

def account_subject(event):
    if event.get('event') in TARGET_EVENTS:
        try:
            data=event.get('data') or '{}'
            if isinstance(data,str):data=json.loads(data)
            subject=data.get('id')
        except (ValueError,TypeError,AttributeError):return None
    else:subject=event.get('actor')
    return subject if type(subject) is int and subject>0 else None

def visible_to(user,event):
    if not user:return False
    user=dict(user)
    if not user.get('enabled'):return False
    if user.get('admin'):return True
    category=event.get('category')
    if category in SHARED:return True
    if category in {'auth','user'}:return account_subject(event)==user['id']
    # Global audit/unknown event categories are not a non-admin subscription grant.
    return False
