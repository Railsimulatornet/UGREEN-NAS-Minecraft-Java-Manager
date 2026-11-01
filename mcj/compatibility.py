"""Only packaged, explicitly tested runtime combinations are selectable."""
def matrix(store):
    entries=(store.get('guard_catalog') or {}).get('artifacts',[])
    return {'single_instance_per_nas':True,'variants':[
        {'minecraft':x['minecraft'],'loader':x['loader'],'java':x.get('java',25),
         'loader_versions':x.get('tested_loaders',[]),'guard_version':x.get('version'),
         'guard_sha256':x['sha256'],'runtime_test':x.get('runtime_test','not_tested'),
         'visitor_client_test':x.get('visitor_client_test','not_verified'),
         'selectable':x.get('runtime_test')=='passed' and x.get('visitor_client_test')=='passed' and x.get('visitor_verified') is True}
        for x in entries if x.get('loader') in {'FABRIC','FORGE','NEOFORGE'}],
        'unsupported':[loader for loader in ['FORGE','FABRIC','NEOFORGE','VANILLA','PAPER','SPIGOT','QUILT','BEDROCK']
                       if not any(x.get('loader')==loader and x.get('runtime_test')=='passed'
                                  and x.get('visitor_client_test')=='passed' for x in entries)]}
