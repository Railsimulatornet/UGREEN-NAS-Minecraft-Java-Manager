"""Unprivileged setup listener: only the setup queue/TLS directory is mounted."""
import json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from mcj import bootstrap,local_tls


def main():
    context=json.loads(os.environ['MCJ_SETUP_CONTEXT']);base=Path('/setup')
    from mcj.service_identity import validate
    uid,gid=validate(context['service_uid'],context['service_gid'])
    if os.geteuid()!=uid or os.getegid()!=gid:raise ValueError('setup_listener_permissions_invalid')
    app=bootstrap.create_app(base,context);cert,key=local_tls.files(base/'tls')
    import uvicorn
    uvicorn.run(app,host='0.0.0.0',port=8090,ssl_certfile=str(cert),ssl_keyfile=str(key),access_log=False,proxy_headers=False,server_header=False)


if __name__=='__main__':main()
