"""Consume only this installation's private, now invalid initial credential file."""
import os,stat


def consume_file(st,user):
    marker=st.get('gui_bootstrap')
    if not isinstance(marker,dict) or marker.get('user_id')!=user['id'] or not user['force_password']:
        return
    path=st.state/'ERSTE-ANMELDUNG.txt'
    try:
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or (hasattr(os,'getuid') and info.st_uid!=os.getuid()):
            return
        path.unlink()
    except FileNotFoundError:pass
    except OSError:return
    st.set('gui_bootstrap',{'user_id':user['id'],'credential_file_removed':True})
