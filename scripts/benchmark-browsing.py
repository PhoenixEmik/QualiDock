#!/usr/bin/env python3
"""Local synthetic directory benchmark; never scans or stresses production storage."""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import tracemalloc

from qualidock.files import FileAccess

parser=argparse.ArgumentParser()
parser.add_argument('--entries',type=int,default=100000)
parser.add_argument('--pages',type=int,default=2)
parser.add_argument('--baseline-file',type=Path)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
assert 2 <= args.entries <= 200000 and 1 <= args.pages <= 10
result={'entries':args.entries,'page_size':500,'pages':args.pages,'scope':'local temporary directory with synthetic empty filenames; not FASTQ analysis or NFS/Lustre throughput'}
with tempfile.TemporaryDirectory(prefix='qualidock-directory-bench-') as temporary:
 root=Path(temporary)
 for index in range(args.entries):
  (root/f'sample_{index//2:06d}_R{index%2+1}.fastq.gz').touch()
 def measure(cls):
  files=cls([root]); snapshots=[]
  original=Path.stat; calls=0
  def counted(path,*positional,**keywords):
   nonlocal calls
   calls+=1
   return original(path,*positional,**keywords)
  Path.stat=counted
  tracemalloc.start()
  try:
   for page in range(args.pages):
    calls=0; start=time.perf_counter()
    response=files.browse(str(root),offset=page*500,limit=500)
    snapshots.append({'page':page,'elapsed_seconds':time.perf_counter()-start,'python_path_stat_calls':calls,'returned':len(response['entries'])})
    assert len(response['entries'])==500 and all(row['paired'] for row in response['entries'])
   _,peak=tracemalloc.get_traced_memory()
  finally:
   Path.stat=original; tracemalloc.stop()
  return {'pages':snapshots,'peak_traced_python_bytes':peak}
 if args.baseline_file:
  spec=importlib.util.spec_from_file_location('qualidock_baseline_files',args.baseline_file)
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  result['before']=measure(module.FileAccess)
 result['after']=measure(FileAccess)
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
