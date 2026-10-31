"""Real Compose regression: a literal game image must not ignore a requested image."""
name='compose_image_selection_contract_and_actual_container_image'
from mcj import controller as c
assert c.PROJECT=='mcj_layout_acceptance_20261025' and c.player_count()==0
before=c.target();before_id=before.id;before_image=before.attrs['Image']
assert before_image=='sha256:f1d1b3390795414d9caea34387e550d4bfd0688a046b3708261640a41b99a82f'
compose=c.ROOT/'docker-compose.yaml';raw=compose.read_bytes();value=json.loads(raw)
value['services']['minecraft']['image']='itzg/minecraft-server:java25@sha256:6fd6f9bb6998b7cd06948ec6ab03fabfdf98ba3f2ec030c44069bec9a6bdf09d'
st.atomic(compose,json.dumps(value,indent=2).encode(),0o640)
environment=c.ROOT/'.env';old_env=environment.read_bytes()
try:
    try:c.deploy_game('itzg/minecraft-server:java25@sha256:0222a05b5bdf82e0d5fc91920d89f02d0df77b6ee51a3c08d748b3864a418524')
    except RuntimeError as exc:assert str(exc)=='compose_game_image_selection_mismatch'
    else:raise AssertionError('A literal Compose image silently ignored the requested image')
    actual=c.target();assert actual.id==before_id and actual.attrs['Image']==before_image
finally:st.atomic(environment,old_env,0o600)
reference='itzg/minecraft-server:java25@sha256:6fd6f9bb6998b7cd06948ec6ab03fabfdf98ba3f2ec030c44069bec9a6bdf09d'
value['services']['minecraft']['image']='${MCJ_GAME_IMAGE:-'+reference+'}'
st.atomic(compose,json.dumps(value,indent=2).encode(),0o640)
_,_,resolved=c.compose_context();assert resolved['services']['minecraft']['image'] in [reference,'itzg/minecraft-server:java25-mcj-f1d1b3390795']
c.gate(True)
try:
    actual=c.deploy_game(reference);assert actual.attrs['Image']==before_image
    _,_,resolved=c.compose_context();assert resolved['services']['minecraft']['image']=='itzg/minecraft-server:java25-mcj-f1d1b3390795'
    c.wait_health();c.guard_integrity()
finally:c.gate(False)
image=c.client.containers.get('mcj_layout_manager').attrs['Image']
fixture.setdefault('coverage',{})[name]={'image_id':image,'checked_at':time.time()}
report(name,{'literal_configuration_rejected_before_container_change':True,'live_container_unchanged_on_rejection':True,
    'approved_reference':reference,'environment_selected_reference':resolved['services']['minecraft']['image'],'actual_game_image':actual.attrs['Image'],'app_image':image,
    'scope':'private organized clone; no public approval','production_changed':False})
