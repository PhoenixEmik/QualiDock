#!/usr/bin/env python3
"""Test-only Picard 3.5.0 RNA metrics qualification; no production QC mode.

Creates only synthetic, isolated BAM/refFlat/interval inputs. Original outputs
are never rewritten. LocalExecutor supplies the application's resource lifecycle.
"""
import argparse
import asyncio
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import resource
import re
import shutil
import time

from qualidock.executor import LocalExecutor
from qualidock.files import approved_file
from qualidock.picard import pdf

STRANDS = ('NONE', 'FIRST_READ_TRANSCRIPTION_STRAND', 'SECOND_READ_TRANSCRIPTION_STRAND')
HEADER = '@HD\tVN:1.6\tSO:coordinate\n@SQ\tSN:chrRNA\tLN:3000\n@RG\tID:rna\tSM:synthetic\tLB:library-A\tPL:ILLUMINA\n'
REF = 'geneA\ttxA\tchrRNA\t+\t100\t900\t200\t800\t2\t100,500,\t300,900,\n'
JAR_SHA = 'b7d97861c3a54ba5a421f5a317f38382f955803862d30ef4aca2bcdc54943631'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def metrics(path):
    """Bounded test contract preserving original field strings and empty cells."""
    if path.stat().st_size > 1024*1024:
        raise ValueError('Qualification report exceeds 1 MiB')
    lines = path.read_text().splitlines()
    marker = '## METRICS CLASS\tpicard.analysis.RnaSeqMetrics'
    if lines.count(marker) != 1:
        raise ValueError('Missing/ambiguous RNA metrics class')
    i = lines.index(marker)+1
    columns = lines[i].split('\t')
    if len(set(columns)) != len(columns) or not {'PF_BASES','PF_ALIGNED_BASES','RIBOSOMAL_BASES','MEDIAN_5PRIME_BIAS'} <= set(columns):
        raise ValueError('Unsupported RNA metrics fields')
    rows = []
    for line in lines[i+1:]:
        if not line:break
        values = line.split('\t')
        if len(values) != len(columns):raise ValueError('Incomplete RNA metric row')
        row = dict(zip(columns, values))
        for key, value in row.items():
            if key not in {'SAMPLE','LIBRARY','READ_GROUP'} and value and not Decimal(value).is_finite():
                raise ValueError('Nonfinite RNA metric')
        rows.append(row)
    if not rows:raise ValueError('No RNA metric population')
    histogram = []
    if '## HISTOGRAM\tjava.lang.Integer' in lines:
        i = lines.index('## HISTOGRAM\tjava.lang.Integer')+1
        columns = lines[i].split('\t')
        for line in lines[i+1:]:
            if not line:break
            values = line.split('\t')
            if len(values) != len(columns):raise ValueError('Incomplete coverage row')
            histogram.append(values)
    return {'rows':rows, 'histogram':histogram}


def sam_record(name, flag, position, cigar='50M', length=50, mate=0, tlen=0):
    mapped = not flag & 4
    return '\t'.join(map(str, (name,flag,'chrRNA' if mapped else '*',position,60 if mapped else 0,cigar if mapped else '*',
                               '=' if mate else '*',mate,tlen,'A'*length,'I'*length,'RG:Z:rna')))


def fixture(directory, kind):
    directory.mkdir()
    ref = REF
    if kind in {'flat-minus','bias-minus'}:
        ref = 'geneA\ttxA\tchrRNA\t-\t100\t900\t200\t800\t2\t100,700,\t500,900,\n'
    if kind.startswith(('flat-','bias-')) or kind=='boundary-spliced':
        minus = kind.endswith('minus')
        # Qualified uniform profiles deliberately cover exon boundaries by one
        # base: 3.5.0 addCoverageCounts omits each alignment block's last base.
        cigar = '200M200N400M' if kind=='boundary-spliced' else '401M199N201M' if minus else '201M199N401M'
        rows = [sam_record('whole',16 if minus else 0,101,cigar,600 if kind=='boundary-spliced' else 602)]
        if kind.startswith('bias'):
            rows.append(sam_record('fiveprime',16 if minus else 0,701 if minus else 101,'201M',201))
    elif kind in {'first-paired','second-paired','mixed-paired'}:
        rows=[]
        for n, flags in enumerate([(99,147)] if kind=='first-paired' else [(83,163)] if kind=='second-paired' else [(99,147),(83,163)]):
            rows.extend([sam_record('pair'+str(n),flags[0],251,mate=551,tlen=350),
                         sam_record('pair'+str(n),flags[1],551,mate=251,tlen=-350)])
    elif kind == 'empty':rows=[]
    else:
        rows=[sam_record(name,flag,pos) for name,flag,pos in (
            ('utr',0,151),('cds1',0,251),('intron',0,401),('cds2',16,551),('qcfail',512,701),('intergenic',0,1201),('rrna',0,1601))]
        rows.append(sam_record('unmapped',4,0))
    # Coordinate-sort in test generation only; never sort user inputs.
    rows.sort(key=lambda line: (line.split('\t')[2]=='*', int(line.split('\t')[3])))
    (directory/'input.sam').write_text(HEADER+'\n'.join(rows)+ ('\n' if rows else ''))
    (directory/'genes.refFlat').write_text(ref)
    (directory/'rrna.interval_list').write_text(HEADER+'chrRNA\t1601\t1650\t+\trRNA\n')
    return directory/'input.bam'


async def qualify_multiqc(root, executable, run):
    from qualidock.import_formats import source_mappings
    before={p:digest(p) for p in root.glob('*.rna_metrics.txt')}
    assert await run('multiqc-version',[executable,'--version'])==0
    version=(root/'multiqc-version.stdout.txt').read_text().strip().split()[-1]
    config={'picard_config':{'s_name_filenames':True}} if version=='1.25.1' else {'use_filename_as_sample_name':['picard']}
    # Duplicate original BAM basenames; only report filenames/namespaces differ.
    reports=[]
    for i,source in enumerate(['flat-plus-NONE','bias-plus-NONE'],1):
        path=root/f'source-{i}'/f'i_{i}.rna_metrics.txt';path.parent.mkdir()
        shutil.copyfile(root/(source+'.rna_metrics.txt'),path);reports.append(path)
    configurations={}
    for name,cfg in [('default',{}),('filenames',config)]:
        directory=root/('multiqc-'+name);directory.mkdir()
        filelist=directory/'inputs.txt';filelist.write_text(''.join(str(p)+'\n' for p in reports))
        config_file=directory/'config.json';config_file.write_text(json.dumps(cfg))
        assert await run('multiqc-'+name,[executable,'--file-list',filelist,'--outdir',directory/'multiqc','--config',config_file,
                                      '--force','--no-version-check','--data-format','json'])==0
        data=json.loads((directory/'multiqc/multiqc_data/multiqc_data.json').read_text())
        rows=data['report_saved_raw_data']['multiqc_picard_RnaSeqMetrics']
        sources=data['report_data_sources']['Picard']['RnaSeqMetrics']
        configurations[name]={'samples':sorted(rows),'source_mapping':sources,'general_statistics':data['report_general_stats_data'],
                              'plot_ids':sorted(data['report_plot_data'])}
        if name=='filenames':
            assert len(rows)==2 and set(sources)==set(rows)
            for report,source_name in zip(reports,['flat-plus-NONE','bias-plus-NONE']):
                names=[sample for sample,path in sources.items() if Path(path)==report]
                assert len(names)==1
                original=metrics(root/(source_name+'.rna_metrics.txt'))['rows'][0]
                mapped=rows[names[0]]
                for key in ['PF_BASES','PF_ALIGNED_BASES','CODING_BASES','UTR_BASES','INTRONIC_BASES','INTERGENIC_BASES','MEDIAN_5PRIME_BIAS','MEDIAN_3PRIME_BIAS','MEDIAN_5PRIME_TO_3PRIME_BIAS']:
                    assert Decimal(str(mapped[key]))==Decimal(original[key]),(version,key,mapped[key],original[key])
                # MultiQC explicitly scales fraction metrics to percent units.
                assert abs(Decimal(str(mapped['PCT_MRNA_BASES']))-Decimal(original['PCT_MRNA_BASES'])*100)<Decimal('0.00000001')
                assert mapped['RIBOSOMAL_BASES'] in {'NA',None}
            assert any('rna' in key.lower() and 'cov' in key.lower() for key in data['report_plot_data'])
            # The production allowlist intentionally has no RNA entry yet.
            # Record that a subsequent adapter must add it, never guess names.
            production=source_mappings(directory/'multiqc/multiqc_data/multiqc_data.json')
            assert production=={}
            configurations[name]['current_production_mapping']=production
    # Original multi-population report is preserved; study official support,
    # rather than silently aggregating ALL_READS and LIBRARY in production.
    for name,source in [('by-library','by-library.rna_metrics.txt'),('incomplete',None)]:
        directory=root/('multiqc-'+name);directory.mkdir()
        path=directory/'input.rna_metrics.txt'
        if source:shutil.copyfile(root/source,path)
        else:
            lines=(root/'flat-plus-NONE.rna_metrics.txt').read_text().splitlines()
            marker=lines.index('## METRICS CLASS\tpicard.analysis.RnaSeqMetrics')
            path.write_text('\n'.join(lines[:marker+2])+'\n')
        listing=directory/'inputs.txt';listing.write_text(str(path)+'\n')
        code=await run('multiqc-'+name,[executable,'--file-list',listing,'--outdir',directory/'multiqc','--force','--no-version-check','--data-format','json'])
        structured=directory/'multiqc/multiqc_data/multiqc_data.json'
        configurations[name]={'exit_code':code,'raw':json.loads(structured.read_text()).get('report_saved_raw_data',{}) if structured.exists() else None}
    assert all(digest(path)==sha for path,sha in before.items()),'MultiQC modified originals'
    return {'version':version,'configurations':configurations,'filename_config':config}


async def qualify(args):
    root=args.output.absolute()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    args.java=str(Path(shutil.which(args.java) or args.java).resolve(strict=True))
    jar=approved_file(args.jar.absolute())
    if digest(jar)!=JAR_SHA:raise ValueError('Not the qualified original Picard 3.5.0 JAR')
    executor=LocalExecutor(1536)
    if args.unmeasured_rss:
        async def unavailable_rss(_group):return 0
        executor.group_memory=unavailable_rss
    commands=[]
    private=root/'private';private.mkdir(mode=0o700)
    environment={**{k:'' for k in ('JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS','REF_PATH','REF_CACHE')},
                 **{k:str(private) for k in ('TMPDIR','TMP','TEMP')},
                 **{k:os.devnull for k in ('R_PROFILE','R_PROFILE_USER','R_ENVIRON','R_ENVIRON_USER')}}
    if args.rscript:
        environment['PATH']=str(Path(args.rscript).resolve().parent)+os.pathsep+os.environ.get('PATH','')
    async def run(label, argv, *, env=None):
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
        started=time.monotonic()
        task=asyncio.create_task(executor.execute(label, list(map(str,argv)), root, root/'execution.log', 1,
                  stdout=root/(label+'.stdout.txt'), stderr=root/(label+'.stderr.txt'),env={**environment,**(env or {})}))
        temporary={'peak_sampled_private_bytes':0,'samples':0,'interval_seconds':0.1}
        async def sample_temporary():
            while not task.done():
                size=0
                for path in private.rglob('*'):
                    try:
                        if path.is_file() and not path.is_symlink():size+=path.stat().st_size
                    except FileNotFoundError:pass
                temporary['samples']+=1
                temporary['peak_sampled_private_bytes']=max(temporary['peak_sampled_private_bytes'],size)
                await asyncio.sleep(0.1)
        monitor=asyncio.create_task(sample_temporary())
        timed_out=False
        try:
            code=await asyncio.wait_for(asyncio.shield(task),args.timeout)
        except asyncio.TimeoutError:
            await executor.cancel(label);code=await task
            timed_out=True
        finally:
            await monitor
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        observed=executor.observations[label]
        if not observed["peak_sampled_rss_bytes"]:observed["peak_sampled_rss_bytes"]=None
        commands.append({'timed_out':timed_out,'label':label,'argv':list(map(str,argv)),'exit_code':code,'wall_seconds':time.monotonic()-started,
                         'child_user_cpu_seconds':after.ru_utime-before.ru_utime,'child_system_cpu_seconds':after.ru_stime-before.ru_stime,
                         **observed,'temporary':temporary})
        # Persist evidence even if a later scientific assertion fails.
        (root/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        if timed_out:raise RuntimeError(f'{label} exceeded qualification timeout')
        return code
    java=[args.java,'-Xms64m','-Xmx512m','-XX:ActiveProcessorCount=1','-XX:-UsePerfData','-Djava.io.tmpdir='+str(private),'-jar',str(jar),'CollectRnaSeqMetrics']
    assert await run('java-version',[args.java,'--version'])==0
    assert re.search(r'(?m)^openjdk 17\.',(root/'java-version.stdout.txt').read_text())
    assert await run('samtools-version',[args.samtools,'--version'])==0
    samtools_version=(root/'samtools-version.stdout.txt').read_text()
    assert 'samtools 1.22.1\n' in samtools_version and 'Using htslib 1.22.1\n' in samtools_version
    assert await run('picard-version',java+['--version'])==1
    assert ((root/'picard-version.stdout.txt').read_text()+(root/'picard-version.stderr.txt').read_text()).splitlines().count('Version:3.5.0')==1
    assert await run('picard-help',java+['--help']) in {0,1}
    if args.rscript:assert await run('R-version',[args.rscript,'--version'])==0
    populations={}
    inputs={}
    async def collect(label,bam,annotation,strand='NONE',extra=(),env=None):
        output=root/(label+'.rna_metrics.txt')
        argv=java+['INPUT='+str(bam),'OUTPUT='+str(output),'REF_FLAT='+str(annotation),'STRAND_SPECIFICITY='+strand,
                   'MINIMUM_LENGTH=500','END_BIAS_BASES=100','RRNA_FRAGMENT_PERCENTAGE=0.8','METRIC_ACCUMULATION_LEVEL=ALL_READS',
                   'ASSUME_SORTED=false','VALIDATION_STRINGENCY=STRICT','CREATE_INDEX=false','CREATE_MD5_FILE=false','TMP_DIR='+str(private)]
        for value in extra:
            key=value.split('=',1)[0]+'='
            if key!='METRIC_ACCUMULATION_LEVEL=':argv=[v for v in argv if not v.startswith(key)]
            argv.append(value)
        code=await run(label,argv,env=env)
        if output.exists():populations[label]=metrics(output)
        return code
    for kind in ['categories','first-paired','second-paired','mixed-paired','flat-plus','flat-minus','bias-plus','bias-minus','boundary-spliced','empty']:
        bam=fixture(root/kind,kind)
        assert await run(kind+'-bam',[args.samtools,'view','-b','-o',bam,bam.with_suffix('.sam')])==0
        for path in bam.parent.iterdir():inputs[path]=digest(path)
        for strand in STRANDS if kind in {'categories','first-paired','second-paired','mixed-paired'} else ['NONE']:
            label=kind+'-'+strand
            assert await collect(label,bam,bam.parent/'genes.refFlat',strand)==0
        if kind=='categories':
            assert await collect('with-rrna',bam,bam.parent/'genes.refFlat',extra=['RIBOSOMAL_INTERVALS='+str(bam.parent/'rrna.interval_list')])==0
            assert await collect('by-library',bam,bam.parent/'genes.refFlat',extra=['METRIC_ACCUMULATION_LEVEL=LIBRARY'])==0
    base=populations['categories-NONE']['rows'][0]
    for key,expected in {'PF_BASES':350,'PF_ALIGNED_BASES':300,'CODING_BASES':100,'UTR_BASES':50,'INTRONIC_BASES':50,'INTERGENIC_BASES':100}.items():
        assert Decimal(base[key])==expected,(key,base[key])
    assert base['RIBOSOMAL_BASES']==base['PCT_RIBOSOMAL_BASES']==''
    for key,numerator,denominator in [('PCT_CODING_BASES',100,300),('PCT_UTR_BASES',50,300),('PCT_INTRONIC_BASES',50,300),('PCT_INTERGENIC_BASES',100,300),('PCT_USABLE_BASES',150,350)]:
        assert abs(Decimal(base[key])-Decimal(numerator)/denominator)<=Decimal('0.0000005')
    rrna=populations['with-rrna']['rows'][0]
    assert rrna['RIBOSOMAL_BASES']=='50' and rrna['INTERGENIC_BASES']=='50'
    assert abs(Decimal(rrna['PCT_RIBOSOMAL_BASES'])-Decimal(1)/6)<=Decimal('0.0000005')
    for kind,expected in [('first-paired',(2,0)),('second-paired',(0,2)),('mixed-paired',(2,2))]:
        for strand,counts in zip(STRANDS,[(0,0),expected,expected[::-1]]):
            row=populations[kind+'-'+strand]['rows'][0]
            assert (int(row['CORRECT_STRAND_READS']),int(row['INCORRECT_STRAND_READS']))==counts
    for kind in ['flat-plus','flat-minus','bias-plus','bias-minus']:
        row=populations[kind+'-NONE']['rows'][0]
        expected=('1.5','0.75','2') if kind.startswith('bias') else ('1','1','1')
        assert [Decimal(row[k]) for k in ('MEDIAN_5PRIME_BIAS','MEDIAN_3PRIME_BIAS','MEDIAN_5PRIME_TO_3PRIME_BIAS')]==list(map(Decimal,expected))
        histogram=populations[kind+'-NONE']['histogram']
        assert [int(v[0]) for v in histogram]==list(range(101))
        if kind.startswith('flat'):assert all(Decimal(v[1])==1 for v in histogram)
    assert not populations['empty-NONE']['histogram']
    assert await collect('length-ineligible',root/'flat-plus/input.bam',root/'flat-plus/genes.refFlat',extra=['MINIMUM_LENGTH=700'])==0
    assert not populations['length-ineligible']['histogram']
    assert not populations['boundary-spliced-NONE']['histogram']
    # Upstream acceptance is studied separately from a future strict local contract.
    bam=root/'categories/input.bam';annotation=bam.parent/'genes.refFlat'
    variants={'wrong-contig':REF.replace('chrRNA','chrOther'), 'malformed':'not\ta\trefFlat\n',
              'duplicate-transcript':REF+REF, 'ambiguous-gene':REF+REF.replace('txA','txB').replace('\t+\t','\t-\t'),
              'wrong-bounds':REF.replace('900','3001')}
    for kind,payload in variants.items():
        target=root/(kind+'.refFlat');target.write_text(payload);inputs[target]=digest(target)
        await collect(kind,bam,target)
    wrong=root/'wrong.interval_list';wrong.write_text(HEADER.replace('LN:3000','LN:3001')+'chrRNA\t1601\t1650\t+\trRNA\n');inputs[wrong]=digest(wrong)
    assert await collect('wrong-rrna-dictionary',bam,annotation,extra=['RIBOSOMAL_INTERVALS='+str(wrong)])!=0
    broken=root/'truncated.bam';broken.write_bytes(bam.read_bytes()[:32]);inputs[broken]=digest(broken)
    assert await collect('truncated',broken,annotation)!=0
    # Missing R must not be hidden by the operator's ordinary PATH.
    no_r=root/'without-R';no_r.mkdir()
    code=await collect('missing-R',root/'flat-plus/input.bam',root/'flat-plus/genes.refFlat',extra=['CHART_OUTPUT='+str(root/'missing-R.pdf')],env={'PATH':str(no_r)})
    assert code!=0
    assert 'Rscript' in (root/'missing-R.stderr.txt').read_text()
    # An explicit FAILURE-only R stand-in lets Java pass --version, then
    # fail during plotting. No scientific metrics/plots are simulated.
    broken_r=root/'broken-R';broken_r.mkdir()
    stub=broken_r/'Rscript';stub.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then echo "Rscript (R) version 4.4.1"; exit 0; fi\nexit 7\n');stub.chmod(0o700)
    assert await collect('plot-error',root/'flat-plus/input.bam',root/'flat-plus/genes.refFlat',extra=['CHART_OUTPUT='+str(root/'plot-error.pdf')],env={'PATH':str(broken_r)})!=0
    assert 'plot-error' in populations
    if args.rscript:
        assert await collect('original-chart',root/'bias-plus/input.bam',root/'bias-plus/genes.refFlat',extra=['CHART_OUTPUT='+str(root/'original-chart.pdf')])==0
        pdf(root/'original-chart.pdf')
    assert all(digest(path)==sha for path,sha in inputs.items()),'Scientific source mutation'
    assert digest(jar)==JAR_SHA,'Picard JAR changed during qualification'
    multiqc_evidence=await qualify_multiqc(root,args.multiqc,run) if args.multiqc else None
    evidence={'multiqc':multiqc_evidence,'status':'upstream-qualified-not-production-integrated','jar_sha256':digest(jar),
              'inputs':{str(p.relative_to(root)):{'sha256':sha,'bytes':p.stat().st_size} for p,sha in inputs.items()},
              'populations':populations,'commands':commands,'private_temporary_bytes_at_end':sum(p.stat().st_size for p in private.rglob('*') if p.is_file()),
              'resource_limits':{'jvm_heap_mb':512,'executor_memory_mb':1536,'cpus':1,'timeout_seconds_per_command':args.timeout,'rss_enforcement':not args.unmeasured_rss},
              'measurement_notes':['CPU includes executor monitoring subprocesses; sequential child CPU deltas.',
                 'RSS is sampled process-tree RSS, not peak allocation or large-data acceptance; zero samples/bytes mean unmeasured.',
                 'Private directory bytes are retained size at end, not peak temporary disk usage.'],
              'decision':'A: propose separately approved native refFlat and ALL_READS-only BAM adapter for subsequent review; no runtime BED12 conversion.'}
    (root/'qualification.json').write_text(json.dumps(evidence,indent=2)+'\n')
    return evidence


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jar',type=Path,required=True)
    parser.add_argument('--java',default='java')
    parser.add_argument('--samtools',default='samtools')
    parser.add_argument('--rscript')
    parser.add_argument('--multiqc',help='Actual optional MultiQC executable; CI requires each compatibility target')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--unmeasured-rss',action='store_true',help='Test-only sandbox fallback: no RSS monitor/enforcement; JVM heap remains bounded; never use for Linux CI acceptance')
    parser.add_argument('--timeout',type=int,default=120)
    args=parser.parse_args()
    result=asyncio.run(qualify(args))
    print(result['status'])
