"""Only packaged, explicitly tested runtime combinations are selectable."""
def matrix(store):
    entries=(store.get('guard_catalog') or {}).get('artifacts',[])
    return {'single_instance_per_nas':True,'variants':[
        {'minecraft':x['minecraft'],'loader':x['loader'],'java':x.get('java',25),
         'loader_versions':x.get('tested_loaders',[]),'guard_version':x.get('version'),
         'guard_sha256':x['sha256'],'runtime_test':x.get('runtime_test','not_tested'),
         'visitor_client_test':x.get('visitor_client_test','not_verified')}
        for x in entries if x.get('loader') in {'FABRIC','NEOFORGE'}],
        'unsupported':['FORGE','VANILLA','PAPER','SPIGOT','QUILT','BEDROCK']}
