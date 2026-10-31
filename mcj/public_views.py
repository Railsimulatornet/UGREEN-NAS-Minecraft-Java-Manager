"""Explicit read-only views: configuration snapshots can contain arbitrary credentials."""
import json
import re


RUNTIME=('version','java','loader','loader_version','memory_mb','container_memory_mb','world')


def runtime(value):
    return {key:value[key] for key in RUNTIME if key in (value or {}) and type(value[key]) in (str,int,float,bool)}


def plan(value):
    result={key:value[key] for key in ('id','created','actor','state') if key in value}
    result['configuration']=runtime(value.get('configuration'))
    report=value.get('report') or {}
    result['report']={key:report[key] for key in ('metadata_checks','runtime_test','approval_required','backup_required','checked') if key in report and type(report[key]) in (str,int,float,bool)}
    return result


def job(value):
    result={key:value[key] for key in ('id','kind','state','created','updated','actor','actor_name','mode','approved','purpose','operation','combined_changes','protection_update') if key in value}
    payload=json.loads(value.get('payload') or '{}')
    details=json.loads(value.get('result') or '{}')
    public_payload={key:payload[key] for key in ('id','name','operation','_scheduled_at') if key in payload and type(payload[key]) in (str,int,float,bool)}
    public_result={}
    if type(details.get('started')) in (int,float):public_result['started']=details['started']
    if isinstance(details.get('progress'),str) and re.fullmatch('[a-z_]{1,80}',details['progress']):public_result['progress']=details['progress']
    # Failure text may contain custom configuration. Readers get a generic failure.
    if details.get('reason'):public_result['reason']='job_failed'
    if isinstance(details.get('runtime'),dict):public_result['runtime']=runtime(details['runtime'])
    result.update(payload=json.dumps(public_payload),result=json.dumps(public_result))
    return result
