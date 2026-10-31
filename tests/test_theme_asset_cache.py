from test_security import environment


def test_theme_asset_revalidates_without_retransmitting_image(environment):
    app,client,credentials,mail=environment
    path='/static/assets/final/branding/server_logo.png'
    first=client.get(path)
    assert first.status_code==200 and len(first.content)>1000
    assert first.headers['cache-control']=='private, max-age=0, must-revalidate'
    etag=first.headers['etag']
    second=client.get(path,headers={'If-None-Match':etag})
    assert second.status_code==304 and second.content==b''
    assert second.headers['cache-control']=='private, max-age=0, must-revalidate'
    assert second.headers['x-content-type-options']=='nosniff'


def test_api_html_and_scripts_remain_non_cacheable(environment):
    app,client,credentials,mail=environment
    for path in ['/','/health','/static/app.js','/client-pack','/client-pack/app.js','/api/auth/me']:
        response=client.get(path)
        assert response.headers['cache-control']=='no-store',path
