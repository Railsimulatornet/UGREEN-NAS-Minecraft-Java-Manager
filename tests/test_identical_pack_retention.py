import hashlib,json,time
from mcj import storage_admin
from test_security import environment,enroll


def test_only_latest_matching_pack_is_marked_current_and_old_equivalent_links_are_revoked(environment):
    app,client,_,_=environment;enroll(environment);st=app.state.store;root=st.state/'client-packs';root.mkdir()
    with st.db() as db:
        for number in [1,2]:
            identifier=str(number)*32;raw=b'owned-pack-'+str(number).encode();(root/(identifier+'.mrpack')).write_bytes(raw)
            db.execute('INSERT INTO client_packs VALUES(?,?,?,?,?,?,?,?)',(identifier,number,time.time(),1,'same-current',hashlib.sha256(raw).hexdigest(),len(raw),json.dumps({'version':'fixture-'+str(number),'runtime':{'version':'26.3','loader':'NEOFORGE','loader_version':'26.3.0.99','java':25},'included':[]})))
        db.execute('INSERT INTO client_pack_links(id,pack_id,actor,created,expires,token_hash) VALUES(?,?,?,?,?,?)',('3'*32,'1'*32,1,time.time(),0,'owned-capability-hash'))
    app.state.rpc=lambda *_:{'fingerprint':'same-current'}
    listed=client.get('/api/client-packs').json()['packs']
    assert [(x['id'],x['current']) for x in listed]==[('2'*32,True),('1'*32,False)]
    assert listed[1]['active_links']==1
    preview=storage_admin.delete(st,root,'client_pack',['1'*32],1,current_fingerprint='same-current')
    assert preview['active_links']==1
    storage_admin.delete(st,root,'client_pack',['1'*32],1,current_fingerprint='same-current',confirmation=preview['confirmation'])
    assert (root/('2'*32+'.mrpack')).is_file() and not (root/('1'*32+'.mrpack')).exists()
    with st.db() as db:assert not db.execute('SELECT 1 FROM client_pack_links').fetchone()
