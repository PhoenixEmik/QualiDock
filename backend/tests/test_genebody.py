"""Genuine CI percentile table, with adversarial contract mutations only in tests."""
from pathlib import Path
import shutil
import pytest
from qualidock import rseqc

FIXTURE = Path(__file__).parent/'fixtures/rseqc-5.0.5/genebody'


def test_original_values_are_not_the_normalized_r_plot():
    data = rseqc.gene_body_profile(FIXTURE/'gene-body.geneBodyCoverage.txt','input')
    assert len(data['rows']) == 100 and data['rows'][0] == ['1','0.0']
    assert data['rows'][-1] == ['100','0.0']
    assert max(float(r[1]) for r in data['rows']) == 2.0
    assert data['status'] == 'available'
    assert '0.5' in (FIXTURE/'gene-body.geneBodyCoverage.r').read_text()


@pytest.mark.parametrize('fault',['missing','duplicate','reordered','nan','inf','negative','identity','extra','empty','oversize','truncated'])
def test_invalid_profiles_never_publish(tmp_path,fault):
    source=(FIXTURE/'gene-body.geneBodyCoverage.txt').read_text()
    lines=[line.split('\t') for line in source.splitlines()]
    if fault == 'missing':lines[0].pop()
    elif fault == 'duplicate':lines[0][10] = lines[0][9]
    elif fault == 'reordered':lines[0][1:3] = ['2','1']
    elif fault in {'nan','inf','negative','empty'}:lines[1][5]={'nan':'NaN','inf':'Infinity','negative':'-1','empty':''}[fault]
    elif fault == 'identity':lines[1][0] = 'other'
    elif fault == 'extra':lines.append(lines[1])
    elif fault == 'truncated':lines[1].pop()
    p=tmp_path/'report.txt';p.write_text('\n'.join('\t'.join(l) for l in lines)+'\n')
    if fault == 'oversize':p.write_bytes(b'x'*(1024*1024+1))
    with pytest.raises(ValueError):rseqc.gene_body_profile(p,'input')


def test_empty_and_constant_are_unavailable_without_inventing_points(tmp_path):
    p=tmp_path/'table.txt';header='Percentile\t'+'\t'.join(map(str,range(1,101)))+'\n'
    p.write_text(header)
    assert rseqc.gene_body_profile(p,'input')['rows'] == []
    for value in ['0.0','1.25']:
        p.write_text(header+'input\t'+'\t'.join([value]*100)+'\n')
        result=rseqc.gene_body_profile(p,'input')
        assert result['status']==('unavailable' if value=='0.0' else 'available')
        assert all(row[1]==value for row in result['rows'])


@pytest.mark.parametrize('options',[{'minimum_length':99},{'minimum_length':True},{'original_plot':'true'},{'minimum_length':10000001},{'arbitrary':'command'}])
def test_strict_upstream_options(options):
    with pytest.raises(ValueError):rseqc.GeneBodyOptions.model_validate({'annotation':'genes',**options})


@pytest.mark.parametrize('payload',[b'',b'\x89PNG\r\n\x1a\n',b'<html>not a PNG</html>'])
def test_corrupt_original_plot_rejected(tmp_path,payload):
    p=tmp_path/'plot.png';p.write_bytes(payload)
    with pytest.raises(ValueError):rseqc.checked_png(p)
