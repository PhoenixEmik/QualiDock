#!/usr/bin/env python3
"""Compare legacy and paginated history payloads using isolated synthetic metadata.

No QC results, source FASTQs or production run stores are used.
"""
import argparse
import json
from pathlib import Path
import platform
import statistics
from tempfile import TemporaryDirectory
import time

from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings
from qualidock.history import invalidation


def benchmark(count, inputs):
    with TemporaryDirectory(prefix='qualidock-history-') as tmp:
        root=Path(tmp).resolve()
        app=create_app(Settings(roots=[root],output=root/'results',frontend=root/'ui',token='synthetic-benchmark-only',allow_root=True))
        with TestClient(app,headers={'Authorization':'Bearer synthetic-benchmark-only'}) as client:
            runs={}
            for n in range(count):
                paths=[f'/synthetic-benchmark/project-{n}/sample-{i:03d}_R1.fastq.gz' for i in range(inputs)]
                run={'id':f'{n:032x}','name':f'Synthetic history {n}','mode':'both','state':'completed','stage':'Synthetic benchmark only','created_at':f'2026-10-{n%28+1:02d}T00:00:00Z','updated_at':'2026-10-16T00:00:00Z','started_at':None,'finished_at':None,'threads':1,'inputs':paths,'sample_count':0,'error':None,'reports':[],
                     'input_outcomes':[{'path':p,'id':f'input{i}','state':'unknown','error':'Synthetic benchmark metadata only'} for i,p in enumerate(paths)],
                     'input_pairing':[{'path':p,'name':p.rsplit('/',1)[1],'paired':False,'pair_key':None,'mate':None,'read':None} for p in paths]}
                runs[run['id']]=run
            app.state.manager.runs=runs
            result={'synthetic':True,'platform':platform.platform(),'runs':count,'inputs_per_run':inputs}
            try:
                for label,url in [('legacy','/api/runs'),('summary_page','/api/history?limit=25')]:
                    elapsed=[]
                    for _ in range(3):
                        start=time.perf_counter();response=client.get(url);elapsed.append(time.perf_counter()-start)
                        assert response.status_code==200,response.text
                    result[label]={'bytes':len(response.content),'api_median_seconds':statistics.median(elapsed)}
                result['legacy_sse_payload_bytes']=len(json.dumps(list(runs.values())).encode())
                result['invalidation_sse_payload_bytes']=len(json.dumps(invalidation(count)).encode())
            finally:
                app.state.manager.runs={}
            return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs',type=int,default=300)
    parser.add_argument('--inputs',type=int,default=250)
    parser.add_argument('--output',type=Path,default=Path('validation/history-benchmark/benchmark.json'))
    args=parser.parse_args()
    if not 1<=args.runs<=1000 or not 1<=args.inputs<=500:
        parser.error('Use 1–1000 histories and 1–500 synthetic inputs per history')
    result=benchmark(args.runs,args.inputs)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
