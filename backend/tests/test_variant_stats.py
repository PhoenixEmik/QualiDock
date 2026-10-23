"""Original native reports and deliberately corrupted copies, never fake evidence."""
import hashlib
import json
from pathlib import Path

import pytest
from qualidock.variant import original, readable

FIX=Path(__file__).parent/'fixtures/bcftools-1.24'
PROVENANCE=json.loads((FIX/'provenance.json').read_text())
VALID=[r for r in PROVENANCE['commands'] if r['exit_code']==0]


def case(name='multisample',samples=True):
    entry=next(r for r in VALID if r['case']==name and r['per_sample']==samples)
    source=Path(entry['argv'][-1])
    header=readable(FIX/'inputs'/source.name)
    return entry,source,header


@pytest.mark.parametrize('entry',VALID,ids=lambda r:r['report'])
def test_every_genuine_original_is_validated_without_changing_strings(entry):
    source=Path(entry['argv'][-1]);path=FIX/entry['report'];header=readable(FIX/'inputs'/source.name)
    before=path.read_bytes();result=original(path,source,header,entry['per_sample'])
    expected=[line.split('\t')[2:] for line in before.decode().splitlines() if line.startswith('SN\t')]
    assert result['summary']['rows']==expected
    assert result['report_sha256']==hashlib.sha256(before).hexdigest()==entry['sha256']
    assert path.read_bytes()==before


def test_counts_overlap_and_gvcf_blocks_are_not_genome_coverage():
    entry,source,header=case('mixed',False);data=original(FIX/entry['report'],source,header,False)
    values=dict(data['summary']['rows'])
    assert values['number of records:']=='6' and values['number of SNPs:']=='2' and values['number of indels:']=='2' and values['number of MNPs:']=='1'
    assert data['tstv']['rows'][0][2]=='0.00' and data['tstv_ratio'] is None
    entry,source,header=case('gvcf',False);values=dict(original(FIX/entry['report'],source,header,False)['summary']['rows'])
    assert values['number of records:']=='2' and values['number of no-ALTs:']=='1'


def test_missing_quality_depth_genotypes_and_zero_are_distinct():
    entry,source,header=case('missing-depth',True);data=original(FIX/entry['report'],source,header,True)
    assert not data['quality_available'] and data['quality']['rows'][0][0]=='.'
    assert not data['site_depth_available'] and not data['genotype_depth_available'] and not data['depth']['rows']
    assert 'average depth' not in data['sample_counts']['columns']
    assert data['sample_counts']['rows'][0][-1]=='1' and data['sample_statistics_available']
    entry,source,header=case('no-genotype',True)
    assert not original(FIX/entry['report'],source,header,True)['sample_statistics_available']
    entry,source,header=case('empty',False)
    assert dict(original(FIX/entry['report'],source,header,False)['summary']['rows'])['number of records:']=='0'


@pytest.mark.parametrize('fault',['missing-tail','missing-newline','version','duplicate-id','wrong-source','duplicate-summary','extra-summary-field','nan','negative','duplicate-column','wrong-columns','missing-substitution','duplicate-depth','wrong-depth-fraction','wrong-ratio','missing-sample','unknown-sample','wrong-set','oversized-line'])
def test_malformed_or_truncated_report_is_not_completed_qc(tmp_path,fault):
    entry,source,header=case();text=(FIX/entry['report']).read_text()
    if fault=='missing-tail':text=text.split('# DP, depth:')[0]
    elif fault=='missing-newline':text=text.rstrip('\n')
    elif fault=='version':text=text.replace('1.24+htslib-1.24','1.24+htslib-1.22.1')
    elif fault=='duplicate-id':text+=f'ID\t0\t{source}\n'
    elif fault=='wrong-source':text=text.replace(f'ID\t0\t{source}',f'ID\t0\t{source}.other')
    elif fault=='duplicate-summary':text+='SN\t0\tnumber of records:\t4\n'
    elif fault=='extra-summary-field':text=text.replace('SN\t0\tnumber of records:\t4','SN\t0\tnumber of records:\t4\textra')
    elif fault=='nan':text=text.replace('TSTV\t0\t2\t2\t1.00','TSTV\t0\t2\t2\tNaN')
    elif fault=='negative':text=text.replace('ST\t0\tA>C\t1','ST\t0\tA>C\t-1')
    elif fault=='duplicate-column':text+='# SN\t[2]id\t[3]key\t[4]value\n'
    elif fault=='wrong-columns':text=text.replace('[3]Quality','[3]Imagined quality')
    elif fault=='missing-substitution':text='\n'.join(l for l in text.splitlines() if not l.startswith('ST\t0\tT>G'))+'\n'
    elif fault=='duplicate-depth':text+='DP\t0\t7\t1\t14.285714\t1\t25.000000\n'
    elif fault=='wrong-depth-fraction':text=text.replace('DP\t0\t22\t0\t0.000000\t1\t25.000000','DP\t0\t22\t0\t0.000000\t1\t24.000000')
    elif fault=='wrong-ratio':text=text.replace('TSTV\t0\t2\t2\t1.00','TSTV\t0\t2\t2\t0.50')
    elif fault=='missing-sample':text='\n'.join(l for l in text.splitlines() if not l.startswith('PSC\t0\tbeta'))+'\n'
    elif fault=='unknown-sample':text=text.replace('PSC\t0\tbeta','PSC\t0\tother')
    elif fault=='wrong-set':text=text.replace('QUAL\t0\t30.0','QUAL\t1\t30.0')
    else:text+='#'+('x'*65536)+'\n'
    path=tmp_path/'deliberately-invalid.stats.txt';path.write_text(text)
    with pytest.raises(ValueError):original(path,source,header,True)


def test_unknown_sections_stay_original_without_inventing_native_metrics(tmp_path):
    entry,source,header=case('snps',False)
    path=tmp_path/'with-original-unknown.stats.txt'
    path.write_bytes((FIX/entry['report']).read_bytes()+b'# FUTURE\t[2]id\t[3]value\nFUTURE\t0\tunknown\n')
    data=original(path,source,header,False)
    assert 'FUTURE' in data['uninterpreted_sections'] and 'FUTURE' not in data
