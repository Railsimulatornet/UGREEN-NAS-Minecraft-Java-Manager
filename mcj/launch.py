"""Direct local HTTPS with a reloadable certificate; proxy installations keep their existing launch."""
import os
from pathlib import Path
import uvicorn
from . import local_tls
from .entry import app


def main():
    base=Path(os.environ.get('MCJ_TLS_DIR','/run/mcj-tls'));cert,key=local_tls.files(base)
    configuration=uvicorn.Config(app,host='0.0.0.0',port=8090,access_log=False,proxy_headers=False,
        ssl_certfile=str(cert),ssl_keyfile=str(key))
    configuration.load()
    app.state.tls_reload=lambda cert,key:configuration.ssl.load_cert_chain(str(cert),str(key))
    uvicorn.Server(configuration).run()


if __name__=='__main__':main()
