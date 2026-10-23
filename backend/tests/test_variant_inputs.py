import asyncio
import gzip
from pathlib import Path
import sys

import pytest
from qualidock.files import FileAccess, PathViolation
from qualidock.tools import detect_tool
from qualidock.variant import Options, readable

HEADER='##fileformat=VCFv4.3\n##contig=<ID=chr1,length=1000>\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n'


def test_variant_kind_is_independent_of_fastq_and_alignment(tmp_path):
    for name in ['sample_R1.vcf','sample_R2.vcf.gz','sample.bcf']:(tmp_path/name).touch()
    entries=FileAccess([tmp_path]).browse(str(tmp_path))['entries']
    assert all(e['kind']=='variant' and not e['paired'] and e['read'] is None for e in entries)


@pytest.mark.parametrize('version,library,expected',[('1.24','1.24',True),('1.24','1.22.1',False),('1.24','1.23.1',False),('1.24','1.23.2',False),('1.24rc1','1.24',False),('1.24','1.24rc1',False),('1.23.2','1.23.2',False),('1.25','1.25',False)])
def test_both_bcftools_and_native_htslib_are_required(tmp_path,version,library,expected):
    exe=tmp_path/'bcftools';exe.write_text(f'#!{sys.executable}\nprint({f"bcftools {version}\nUsing htslib {library}"!r})\n');exe.chmod(0o700)
    assert asyncio.run(detect_tool('bcftools',str(exe)))['compatible'] is expected


@pytest.mark.parametrize('compressed',[False,True])
def test_bounded_header_identity_and_missing_optional_fields(tmp_path,compressed):
    path=tmp_path/('case.vcf.gz' if compressed else 'case.vcf')
    if compressed:
        with gzip.open(path,'wb') as stream:stream.write(HEADER.encode())
    else:path.write_text(HEADER)
    info=readable(path)
    assert info['samples']==[] and info['tags']=={'INFO':[],'FORMAT':[]} and info['source_snapshot']


@pytest.mark.parametrize('fault',['duplicate-samples','no-format','missing-column','unknown-version','duplicate-version','missing-newline','oversized-line','oversized-header','compression','bcf','reserved-path'])
def test_invalid_headers_are_not_invented_or_repaired(tmp_path,monkeypatch,fault):
    path=tmp_path/'invalid.vcf';text=HEADER
    if fault=='duplicate-samples':text=text.rstrip()+'\tFORMAT\tsame\tsame\n'
    elif fault=='no-format':text=text.rstrip()+'\tsample\n'
    elif fault=='missing-column':text=text.replace('\tINFO','')
    elif fault=='unknown-version':text=text.replace('VCFv4.3','VCFv4.5')
    elif fault=='duplicate-version':text=text.replace('##contig','##fileformat=VCFv4.3\n##contig')
    elif fault=='missing-newline':text=text.rstrip('\n')
    elif fault=='oversized-line':monkeypatch.setattr('qualidock.variant.LINE_LIMIT',10)
    elif fault=='oversized-header':monkeypatch.setattr('qualidock.variant.HEADER_LIMIT',10)
    elif fault=='compression':path=path.with_suffix('.vcf.gz')
    elif fault=='bcf':path=path.with_suffix('.bcf')
    elif fault=='reserved-path':path=path.with_name('input##idx##escape.vcf')
    path.write_text(text)
    with pytest.raises(ValueError):readable(path)


def test_variant_input_root_and_symlink_escape(tmp_path):
    root=tmp_path/'authorized';root.mkdir();outside=tmp_path/'other.vcf';outside.write_text(HEADER)
    (root/'escape.vcf').symlink_to(outside)
    access=FileAccess([root])
    for raw in [str(outside),str(root/'escape.vcf'),str(root/'..'/'other.vcf')]:
        with pytest.raises(PathViolation):access.resolve(raw)
    assert not access.browse(str(root))['entries']


@pytest.mark.parametrize('options',[{'per_sample':'yes'},{'multiqc':1},{'filter':'PASS'},{'regions':'chr1'},{'create_index':True}])
def test_only_explicit_read_only_options(options):
    with pytest.raises(ValueError):Options.model_validate(options)


@pytest.mark.parametrize('flag',[4,8,16])
def test_optional_gzip_headers_are_bounded_before_decompression(tmp_path,flag):
    path=tmp_path/'header.vcf.gz'
    path.write_bytes(b'\x1f\x8b\x08'+bytes([flag])+b'\x00'*6+(b'\xff\xff' if flag==4 else b'')+b'x'*70000)
    with pytest.raises(ValueError):readable(path)
