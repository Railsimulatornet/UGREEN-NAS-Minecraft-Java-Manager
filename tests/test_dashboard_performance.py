import copy,json,time
from types import SimpleNamespace
from test_security import environment,enroll
from mcj.telemetry import DockerSamples,normalized_cpu


def test_one_shot_samples_require_two_same_runtime_counters_and_reset_after_restart():
 reads=[];stats={'cpu_stats':{'cpu_usage':{'total_usage':100},'system_cpu_usage':1000,'online_cpus':8}}
 def read(**kwargs):reads.append(kwargs);return copy.deepcopy(stats)
 container=SimpleNamespace(id='a',attrs={'State':{'StartedAt':'first'}},stats=read)
 sampler=DockerSamples();first=sampler.collect(container)
 assert first['precpu_stats']=={} and normalized_cpu(first,{})['cpu_normalized_percent'] is None
 stats['cpu_stats']['cpu_usage']['total_usage']=200;stats['cpu_stats']['system_cpu_usage']=2000
 second=sampler.collect(container);assert normalized_cpu(second,{})['cpu_normalized_percent']==10
 assert first['cpu_stats']['cpu_usage']['total_usage']==100
 container.attrs['State']['StartedAt']='restarted';third=sampler.collect(container);assert normalized_cpu(third,{})['cpu_normalized_percent'] is None
 container.id='replacement';assert sampler.collect(container)['precpu_stats']=={}
 assert all(x=={'stream':False,'one_shot':True} for x in reads)


def test_one_shot_falls_back_only_for_unsupported_docker_api():
 from docker.errors import InvalidVersion
 reads=[]
 def read(**kwargs):
  reads.append(kwargs)
  if kwargs.get('one_shot'):raise InvalidVersion('API too old')
  return {'legacy':'real sample'}
 assert DockerSamples().collect(SimpleNamespace(stats=read))=={'legacy':'real sample'}
 assert reads==[{'stream':False,'one_shot':True},{'stream':False}]


def test_compact_jobs_keep_active_and_recent_history_full_details_remain_available(environment):
 app,client,creds,mail=environment;enroll(environment);st=app.state.store;now=time.time()
 large={'started':now-2,'progress':'test_running','runtime':{'properties':{'fixture':'x'*10000}},'installed_mods':[{'filename':'fixture.jar'}],'phases':[{'stage':'preparing','at':now-2}]}
 with st.db() as db:
  for i in range(60):db.execute('INSERT INTO jobs(id,kind,state,created,updated,actor,mode,payload,result,approved) VALUES(?,?,?,?,?,?,?,?,?,1)',(str(i).zfill(32),'backup','succeeded',now-i,now,1,'manual',json.dumps({'configuration':{'fixture':'x'*1000}}),json.dumps(large)))
  for i,state in enumerate(['queued','running','planned'],60):db.execute('INSERT INTO jobs(id,kind,state,created,updated,actor,mode,payload,result,approved) VALUES(?,?,?,?,?,?,?,?,?,1)',(str(i).zfill(32),'restore_test',state,now-i,now,1,'manual',json.dumps({'id':'a'*32}),json.dumps(large)))
 full=client.get('/api/jobs');summary=client.get('/api/jobs?summary=true')
 assert full.status_code==summary.status_code==200
 assert len(full.json())==63 and len(summary.json())==6
 assert {x['state'] for x in summary.json()}=={'queued','running','planned','succeeded'}
 assert len(summary.content)<len(full.content)/50
 for x in summary.json():
  assert 'runtime' not in json.loads(x['result']) and 'configuration' not in json.loads(x['payload'])
  assert json.loads(x['result'])['progress']=='test_running'
 assert json.loads(full.json()[-1]['result'])['runtime']['properties']['fixture']=='x'*10000
 assert client.get('/api/jobs?summary=invalid').status_code==422
