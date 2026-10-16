"""Actual small FASTQ bytes, not inferred FastQC aggregate statistics."""
import gzip
import hashlib
from pathlib import Path
import pytest
from qualidock.integrity import scan_file, compare_pairs, snapshot


def entry(path,offset=33):
 return {'id':path.stem,'path':str(path),'snapshot':snapshot(path.stat()),'phred_offset':offset,'encoding_source':'Explicit test encoding','qc_input_snapshot_verified':True}


def fastq(ids,read=1):
 return b''.join(f'@{name}/{read}\nACGTN\n+\n?I!I5\n'.encode() for name in ids)


@pytest.mark.parametrize('compressed',[False,True])
def test_complete_scan_exact_counts_qualities_checksums_and_immutable_sources(tmp_path,compressed):
 data=fastq(['one','two']);path=tmp_path/('reads.fastq.gz' if compressed else 'reads.fastq')
 path.write_bytes(gzip.compress(data,mtime=0) if compressed else data);before=path.read_bytes()
 result=scan_file(entry(path))
 assert result['state']=='passed' and result['coverage']=='full'
 assert result['records_scanned']==2 and result['bases_scanned']==10
 assert result['q20_bases']==8 and result['q30_bases']==6 and result['quality_bases']==10
 assert result['sha256']==hashlib.sha256(before).hexdigest()
 assert result['gzip_crc']==('verified' if compressed else 'not_applicable')
 assert path.read_bytes()==before


def test_multi_member_gzip_and_wrapped_fastq_are_supported(tmp_path):
 path=tmp_path/'multi.fastq.gz';path.write_bytes(gzip.compress(b'@a/1 description\nACG\nTN\n+a/1\nIII\nII\n')+gzip.compress(fastq(['b'])))
 result=scan_file(entry(path))
 assert result['state']=='passed' and result['records_scanned']==2
 assert result['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('data',[b'@x\nACGT\n+\nIII\n',b'@x\nACGT\n+\nIIIII\n',b'x\nACGT\n+\nIIII\n',b'@x\nACZT\n+\nIIII\n',b'@x\nACGT\n+y\nIIII\n',b'@x\nACGT\n+\nII I\n'])
def test_malformed_records_fail_without_complete_checksums(tmp_path,data):
 path=tmp_path/'bad.fastq';path.write_bytes(data);result=scan_file(entry(path))
 assert result['state']=='failed' and result['error']
 assert result['sha256'] is None and result['id_order_sha256'] is None


@pytest.mark.parametrize('corruption',['crc','truncation','deflate'])
def test_corrupt_gzip_fails(tmp_path,corruption):
 data=bytearray(gzip.compress(fastq(['a','b']),mtime=0))
 if corruption=='crc':data[-8]^=1
 elif corruption=='truncation':data=data[:-6]
 else:data[12]^=255
 path=tmp_path/'corrupt.fastq.gz';path.write_bytes(data);result=scan_file(entry(path))
 assert result['state']=='failed' and result['sha256'] is None


def test_quick_partial_scan_is_never_complete_or_pair_verified(tmp_path):
 paths=[tmp_path/f'R{read}.fastq.gz' for read in [1,2]]
 for read,path in enumerate(paths,1):path.write_bytes(gzip.compress(fastq(['a','b','c'],read)))
 results=[scan_file(entry(path),'quick',1) for path in paths]
 assert all(r['state']=='not_evaluated' and r['records_scanned']==1 and r['sha256'] is None for r in results)
 pairs=compare_pairs([{'id':'pair','r1':str(paths[0]),'r2':str(paths[1])}],results)
 assert pairs[0]['state']=='not_evaluated'


@pytest.mark.parametrize('right,expected',[(['a','b'],'passed'),(['b','a'],'failed'),(['a'],'failed'),(['a','wrong'],'failed')])
def test_pair_order_and_count_are_independent_checks(tmp_path,right,expected):
 left=tmp_path/'L.fastq';mate=tmp_path/'R.fastq';left.write_bytes(fastq(['a','b']));mate.write_bytes(fastq(right,2))
 results=[scan_file(entry(path)) for path in [left,mate]]
 pair={'id':'pair','r1':str(left),'r2':str(mate)}
 assert compare_pairs([pair],results)[0]['state']==expected
 assert compare_pairs([pair],results[:1])[0]['state']=='failed'


def test_unknown_encoding_does_not_fabricate_q20_q30(tmp_path):
 path=tmp_path/'reads.fastq';path.write_bytes(fastq(['a']))
 result=scan_file(entry(path,None))
 assert result['state']=='passed' and result['q20_bases'] is None and result['q30_bases'] is None


def test_changed_source_or_unavailable_input_cannot_pass(tmp_path):
 path=tmp_path/'reads.fastq';path.write_bytes(fastq(['a']));before=entry(path)
 path.write_bytes(fastq(['a','b']))
 assert scan_file(before)['state']=='failed'
 assert scan_file({**before,'preflight_error':'Input unavailable'})['state']=='failed'


def test_empty_and_zero_length_records_remain_explicit(tmp_path):
 path=tmp_path/'empty.fastq.gz';path.write_bytes(gzip.compress(b''));result=scan_file(entry(path))
 assert result['state']=='passed' and result['records_scanned']==result['bases_scanned']==0
 path.write_bytes(gzip.compress(b'@zero\n\n+\n\n'))
 result=scan_file(entry(path));assert result['state']=='passed' and result['records_scanned']==1 and result['bases_scanned']==0


def test_gzip_magic_and_genuine_fixture_ids_counts_and_values():
 from qualidock.metrics import parse_report
 root=Path(__file__).parent/'fixtures/fastqc-0.13.0'
 results=[]
 for read in ['R1','R2']:
  path=(root/f'coverage_{read}.fastq.gz').resolve()
  result=scan_file(entry(path));results.append(result)
  original=parse_report(root/f'coverage_{read}_fastqc',f'coverage_{read}')
  assert result['state']=='passed' and result['records_scanned']==original['total_sequences']
  assert result['bases_scanned']>=result['records_scanned']
 assert compare_pairs([{'id':'fixture-pair','r1':results[0]['path'],'r2':results[1]['path']}],results)[0]['state']=='passed'


def test_compressed_content_without_gz_suffix_is_identified_by_magic(tmp_path):
 path=tmp_path/'reads.fastq';path.write_bytes(gzip.compress(fastq(['a'])))
 result=scan_file(entry(path));assert result['state']=='passed' and result['gzip_crc']=='verified'


def test_queued_mate_is_not_falsely_reported_as_missing():
 pair={'id':'p','r1':'/a','r2':'/b'}
 result=compare_pairs([pair],[],{'/a','/b'})
 assert result[0]['state']=='not_evaluated'
