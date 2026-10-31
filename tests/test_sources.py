import hashlib,httpx,pytest
from mcj.sources import reference,download_curseforge

def test_provider_urls_are_bound_to_official_hosts_and_project_paths():
    assert reference('https://www.curseforge.com/minecraft/mc-mods/create')['kind']=='mod'
    assert reference('https://www.curseforge.com/minecraft/modpacks/aeronautics')['kind']=='pack'
    assert reference('https://modrinth.com/mod/lithium/version/xS0Q8LSi')['file_id']=='xS0Q8LSi'
    for value in ['http://curseforge.com/minecraft/mc-mods/create','https://curseforge.com.evil.test/minecraft/mc-mods/create',
                  'https://user:private@curseforge.com/minecraft/mc-mods/create','https://www.curseforge.com:private/minecraft/mc-mods/create',
                  'https://www.curseforge.com/minecraft/mc-mods/create?token=private']:
        with pytest.raises(ValueError,match='invalid_mod_source_url'):reference(value)

def test_official_cdn_redirect_does_not_receive_api_key(monkeypatch):
    import mcj.sources as sources
    payload=b'bounded-provider-file';requests=[];original=httpx.Client
    def handle(request):
        requests.append(request)
        assert 'x-api-key' not in request.headers
        if request.url.host=='edge.forgecdn.net':return httpx.Response(302,headers={'Location':'https://mediafilez.forgecdn.net/files/file.jar'})
        return httpx.Response(200,content=payload)
    monkeypatch.setattr(sources.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handle),**kwargs))
    file={'downloadUrl':'https://edge.forgecdn.net/files/file.jar','fileLength':len(payload),'hashes':[{'algo':1,'value':hashlib.sha1(payload).hexdigest()}]}
    assert download_curseforge(file)==payload and len(requests)==2

def test_redirect_outside_provider_network_is_rejected(monkeypatch):
    import mcj.sources as sources
    original=httpx.Client;requests=[]
    def handle(request):
        requests.append(request);return httpx.Response(302,headers={'Location':'https://outside.test/file.jar'})
    monkeypatch.setattr(sources.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handle),**kwargs))
    file={'downloadUrl':'https://edge.forgecdn.net/files/file.jar','fileLength':1,'hashes':[{'algo':1,'value':'0'*40}]}
    with pytest.raises(ValueError,match='mod_download_source_invalid'):download_curseforge(file)
    assert len(requests)==1
