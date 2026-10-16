"""Synthetic metadata only: no fabricated QC results are used for history scaling."""
import asyncio
import json
import pytest
from qualidock.history import page, invalidation
from qualidock.app import create_app


def records(count=105):
 return {f'{n:032x}':{'id':f'{n:032x}','name':f'History {n:03d}','mode':'fastqc' if n%2 else 'both','state':'failed' if n%3==0 else 'completed','created_at':f'2026-10-{n%28+1:02d}T00:00:00Z','finished_at':None if n%3==0 else f'2026-10-{n%28+1:02d}T01:00:00Z','inputs':['/synthetic/'+str(i) for i in range(250)],'input_outcomes':[{'path':'/private/large-metadata','state':'unknown'}]} for n in range(count)}


def test_history_pages_are_bounded_disjoint_filtered_and_lightweight():
 runs=records();first=page(runs,7,limit=25);second=page(runs,7,limit=25,offset=25)
 assert len(first['items'])==len(second['items'])==25
 assert not {r['id'] for r in first['items']} & {r['id'] for r in second['items']}
 assert first['total']==105 and all(r['input_count']==250 for r in first['items'])
 assert all('inputs' not in r and 'input_outcomes' not in r for r in first['items'])
 selected=page(runs,7,search='History 00',state='failed',mode='both')
 assert all(r['state']=='failed' and r['mode']=='both' and 'History 00' in r['name'] for r in selected['items'])
 finished=page(runs,7,order='finished-desc',limit=100)
 assert finished['items'][-1]['finished_at'] is None
 assert page(runs,7,offset=10000)['offset']==100
 assert len(json.dumps(first)) < len(json.dumps(list(runs.values())))//10
 assert invalidation(7)=={'revision':7}


@pytest.mark.parametrize('kwargs',[{'offset':-1},{'limit':101},{'state':'invalid'},{'mode':'invalid'},{'order':'invalid'},{'search':'x'*121}])
def test_invalid_history_requests_rejected(kwargs):
 with pytest.raises(ValueError):page(records(),0,**kwargs)


def test_history_api_keeps_legacy_and_rejects_stale_snapshots(client,setup):
 settings,_=setup
 manager=client.app.state.manager
 original=manager.runs;manager.runs=records()
 try:
  first=client.get('/api/history?limit=10').json()
  assert len(first['items'])==10 and first['total']==105
  legacy=client.get('/api/runs').json()
  assert len(legacy)==105 and len(legacy[0]['inputs'])==250
  assert client.get('/api/history',params={'revision':manager.revision+1}).status_code==409
  manager.revision+=1
  assert client.get('/api/history',params={'revision':first['revision']}).status_code==409
 finally:manager.runs=original


def test_invalidation_event_is_small_and_reconnect_always_refreshes(setup):
 settings,_=setup;app=create_app(settings);manager=app.state.manager
 manager.runs=records();manager.revision=105
 endpoint=next(route.endpoint for route in app.routes if route.path=='/api/events')
 class Request:
  async def is_disconnected(self):return False
 async def first(format):
  response=await endpoint(Request(),format=format)
  body=await anext(response.body_iterator)
  await response.body_iterator.aclose()
  return body
 for _ in range(2):
  body=asyncio.run(first('invalidation'))
  assert 'event: revision' in body and '"revision": 105' in body and len(body)<100
 legacy=asyncio.run(first('legacy'))
 assert 'event: runs' in legacy and '/synthetic/' in legacy
