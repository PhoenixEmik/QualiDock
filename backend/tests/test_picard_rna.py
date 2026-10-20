"""Production contract checks use unchanged genuine 3.5.0 report fixtures."""
import asyncio
from dataclasses import replace
from pathlib import Path
import pytest
from qualidock.config import Settings
from qualidock import picard_rna as rna
from test_picard_rna_qualification import STUDY,FIX


@pytest.mark.parametrize('name',[p.name for p in FIX.glob('*.rna_metrics.txt') if p.name!='by-library.rna_metrics.txt'])
def test_all_original_reports_preserve_exact_values(name):
    original=STUDY.metrics(FIX/name);parsed=rna.parse(FIX/name)
    assert dict(zip(parsed['metrics']['columns'],parsed['metrics']['rows'][0]))==original['rows'][0]
    assert parsed['histogram']['rows']==original['histogram']
    assert parsed['coverage_available']==bool(original['histogram'])
    assert parsed['units']['PCT_CODING_BASES']=='fraction'
    if not parsed['coverage_available']:assert original['rows'][0]['MEDIAN_5PRIME_BIAS']=='0'


@pytest.mark.parametrize('fault',['truncated','class','columns','duplicate','population','negative','nan','fraction','category','missing','bin','duplicate-bin','rrna'])
def test_malformed_reports_never_become_scientific_results(tmp_path,fault):
    raw=(FIX/'flat-plus-NONE.rna_metrics.txt').read_text()
    if fault=='truncated':raw=raw.rsplit('\n100\t',1)[0]
    elif fault=='class':raw=raw.replace('picard.analysis.RnaSeqMetrics','picard.analysis.InsertSizeMetrics')
    elif fault=='columns':raw=raw.replace('PF_BASES\t','OTHER\t')
    elif fault=='duplicate':raw+=raw
    elif fault=='population':raw=(FIX/'by-library.rna_metrics.txt').read_text()
    elif fault=='negative':raw=raw.replace('\n0\t1\n','\n0\t-1\n')
    elif fault=='nan':raw=raw.replace('\n0\t1\n','\n0\tNaN\n')
    elif fault=='fraction':raw=raw.replace('0.664452','66.4452')
    elif fault=='category':raw=raw.replace('602\t602\t','602\t603\t')
    elif fault=='missing':raw=raw.replace('602\t602\t','\t602\t')
    elif fault=='bin':raw=raw.replace('\n100\t1','\n101\t1')
    elif fault=='duplicate-bin':raw=raw.replace('\n99\t1','\n98\t1')
    elif fault=='rrna':raw=raw.replace('602\t602\t\t','602\t602\t0\t')
    path=tmp_path/'report';path.write_text(raw)
    with pytest.raises(ValueError):rna.parse(path)


@pytest.fixture
def annotations(tmp_path):
    ref=tmp_path/'genes.refFlat';ref.write_text(STUDY.REF)
    intervals=tmp_path/'rrna.interval_list';intervals.write_text(STUDY.HEADER+'chrRNA\t1601\t1650\t+\trRNA\n')
    return Settings(roots=[tmp_path],output=tmp_path/'out',frontend=tmp_path/'web',rna_refflat_annotations={'genes':str(ref)},rrna_intervals={'rrna':str(intervals)}),ref,intervals


def test_approved_native_identity_and_dictionary_contract(annotations):
    cfg,ref,intervals=annotations
    first=rna.approved(cfg,'genes');rrna=rna.approved(cfg,'rrna','rrna')
    assert first['sha256']==STUDY.digest(ref) and rrna['sha256']==STUDY.digest(intervals)
    assert first['contigs']=={'chrRNA':900} and rrna['contigs']=={'chrRNA':3000}
    assert 'not independent' in first['identity']
    assert rna.listing(cfg,'refflat')==[{'id':'genes','available':True,'error':None}]
    class Manager:settings=cfg
    run={'qc':{'annotation':first,'rrna':rrna}}
    asyncio.run(rna.verify_annotations(Manager(),run,{'chrRNA':3000}))
    for dictionary in ({'chrRNA':2999},{'chrOther':3000}):
        with pytest.raises(ValueError):asyncio.run(rna.verify_annotations(Manager(),run,dictionary))
    ref.write_text(STUDY.REF.replace('geneA','geneB'))
    with pytest.raises(ValueError,match='changed'):asyncio.run(rna.verify_annotations(Manager(),run,{'chrRNA':3000}))


@pytest.mark.parametrize('fault',['duplicate','gene-strand','names','overlap','count','bounds','cds','fields','oversize','link','permissions','relative'])
def test_bad_refflat_is_rejected_before_execution(annotations,fault):
    cfg,ref,_=annotations;raw=ref.read_text()
    if fault=='duplicate':raw+=raw
    elif fault=='gene-strand':raw+=raw.replace('txA','txB').replace('\t+\t','\t-\t')
    elif fault=='names':raw=raw.replace('geneA','txA')
    elif fault=='overlap':raw=raw.replace('100,500,','100,200,')
    elif fault=='count':raw=raw.replace('\t2\t','\t3\t')
    elif fault=='bounds':raw=raw.replace('300,900,','300,950,')
    elif fault=='cds':raw=raw.replace('\t200\t800\t','\t200\t950\t')
    elif fault=='fields':raw+='\textra\n'
    elif fault=='oversize':raw+='x'*16385
    ref.write_text(raw)
    if fault=='link':
        target=ref.with_suffix('.real');ref.rename(target);ref.symlink_to(target)
    elif fault=='permissions':ref.chmod(0o666)
    elif fault=='relative':cfg=replace(cfg,rna_refflat_annotations={'genes':'genes.refFlat'})
    with pytest.raises(ValueError):rna.approved(cfg,'genes')
    assert rna.listing(cfg,'refflat')[0]['available'] is False


@pytest.mark.parametrize('fault',['zero','outside','dictionary','header','empty','repeated'])
def test_bad_rrna_intervals_are_rejected(annotations,fault):
    cfg,_,path=annotations;raw=path.read_text()
    if fault=='zero':raw=raw.replace('\t1601\t','\t0\t')
    elif fault=='outside':raw=raw.replace('\t1650\t','\t3001\t')
    elif fault=='dictionary':raw=raw.replace('@SQ\t','@SQ\tSN:duplicate\t')
    elif fault=='header':raw+='@SQ\tSN:other\tLN:10\n'
    elif fault=='empty':raw=STUDY.HEADER
    elif fault=='repeated':raw=raw.replace('@RG', '@SQ\tSN:chrRNA\tLN:3000\n@RG')
    path.write_text(raw)
    with pytest.raises(ValueError):rna.approved(cfg,'rrna','rrna')


def test_explicit_strand_and_no_unqualified_parameters():
    for strand in STUDY.STRANDS:assert rna.Options(annotation='genes',strand=strand).strand==strand
    for values in ({'annotation':'genes'},{'annotation':'genes','strand':'auto'},{'annotation':'genes','strand':'NONE','by_library':True}):
        with pytest.raises(ValueError):rna.Options.model_validate(values)


@pytest.mark.parametrize('fault',['value','missing-source','unknown-trace','missing-trace','changed-point','duplicate-trace','fake-unavailable'])
def test_multiqc_verification_rejects_changed_or_ambiguous_evidence(tmp_path,fault):
    import json
    from qualidock import multiqc
    report=rna.parse(FIX/'flat-plus-NONE.rna_metrics.txt')
    raw={k:float(v)*100 if k.startswith('PCT_') and v else v or 'NA' for k,v in zip(rna.COLUMNS[:-3],report['metrics']['rows'][0][:-3])}
    line={'name':'sample','pairs':report['histogram']['rows']}
    names={'report':'sample'}
    run={'qc':{'results':[{'report':'report','state':'completed','picard':report}]}}
    lines=[line]
    if fault=='value':raw['CODING_BASES']='401'
    elif fault=='missing-source':names={'report':None}
    elif fault=='unknown-trace':line['name']='other'
    elif fault=='missing-trace':lines=[]
    elif fault=='changed-point':line['pairs']=[*line['pairs']];line['pairs'][0]=['0','2']
    elif fault=='duplicate-trace':lines=[line,line]
    elif fault=='fake-unavailable':report['coverage_available']=False
    data={'report_saved_raw_data':{'multiqc_picard_RnaSeqMetrics':{'sample':raw}},'report_plot_data':{'picard_rna_coverage':{'datasets':[{'lines':lines}]}}}
    directory=tmp_path/'multiqc/multiqc_data';directory.mkdir(parents=True)
    (directory/'multiqc_data.json').write_text(json.dumps(data))
    with pytest.raises(ValueError):asyncio.run(multiqc.verify_picard_rna(tmp_path,run,names))
