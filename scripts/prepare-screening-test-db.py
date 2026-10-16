#!/usr/bin/env python3
"""Build the pinned tiny offline Kraken2 test DB using a caller-provided tool.

No downloads/installations and no production reference claims. Output must be new.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

SOURCE='e1a819d985d1a257e20a8fc57eb27a5d51f4c39e'
ROOT=Path(__file__).resolve().parents[1]

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--kraken2-dir',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 tool=(args.kraken2_dir/'kraken2-build').resolve(strict=True);destination=args.output.expanduser().absolute()
 if destination.exists() or destination.is_symlink() or destination.parent.resolve()!=destination.parent:parser.error('Choose a new output directory under an existing canonical parent')
 refs=ROOT/'backend/tests/fixtures/screening/references';destination.mkdir(mode=0o700);(destination/'taxonomy').mkdir(mode=0o700)
 for name in ('nodes.dmp','names.dmp'):shutil.copyfile(refs/name,destination/'taxonomy'/name)
 library=destination/'references.fa';library.write_bytes(b''.join(path.read_bytes() for path in sorted(refs.glob('*.fa'))))
 with (destination/'build.log').open('wb') as log:
  subprocess.run([str(tool),'--db',str(destination),'--add-to-library',str(library),'--no-masking'],check=True,stdout=log,stderr=subprocess.STDOUT)
  subprocess.run([str(tool),'--db',str(destination),'--build','--threads','1','--subblock-size','8192','--no-masking'],check=True,stdout=log,stderr=subprocess.STDOUT)
 version=subprocess.run([str(tool),'--version'],check=True,capture_output=True,text=True).stdout.strip()
 files=[]
 for name in ('hash.k2d','opts.k2d','taxo.k2d'):
  with (destination/name).open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
  files.append({'name':name,'bytes':(destination/name).stat().st_size,'sha256':sha})
 config={'id':'official-viral-test','name':'Official tiny viral test reference — NOT a production database','version':SOURCE+'-nomask-v1',
         'source':'https://github.com/DerrickWood/kraken2/tree/'+SOURCE+'/data',
         'reference_taxids':[line.split('\t')[0] for line in (refs/'nodes.dmp').read_text().splitlines()],
         'path':str(destination)}
 proof={'tool_version':version,'upstream_commit':SOURCE,'build_options':{'masking':False,'threads':1,'subblock_size':8192},'database':config,'files':files,'purpose':'Offline regression fixture only; does not cover yeast/human/all microbes. NCBI-derived reference subset and fixed simulated reads are not an assay-wide contamination validation.'}
 (destination/'qualidock-fixture-provenance.json').write_text(json.dumps(proof,indent=2)+'\n')
 print(json.dumps([config],ensure_ascii=True))

if __name__=='__main__':main()
