"""Tiny genuine execution measurements, not representative performance acceptance."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest
from test_variant_multiqc import TOOL, MULTIQC

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('variant_benchmark',ROOT/'scripts/benchmark-analysis.py')
benchmark=importlib.util.module_from_spec(spec);spec.loader.exec_module(benchmark)


@pytest.mark.skipif(not TOOL or not MULTIQC,reason='Actual BCFtools + MultiQC required')
@pytest.mark.parametrize('multiqc',[False,True])
def test_existing_benchmark_retains_actual_variant_resource_evidence(tmp_path,monkeypatch,multiqc):
    monkeypatch.setenv('QUALIDOCK_BCFTOOLS',TOOL);monkeypatch.setenv('QUALIDOCK_MULTIQC',MULTIQC)
    source=ROOT/'backend/tests/fixtures/bcftools-1.24/inputs/multisample-bcf.bcf';output=tmp_path/'measured'
    args=benchmark.parser().parse_args(['--mode','bcftools','--variant-per-sample','--input',str(source),'--output',str(output),'--hash-inputs','--memory-mb','1024',*(['--multiqc'] if multiqc else [])])
    benchmark.main(args)
    data=json.loads((output/'benchmark.json').read_text())
    assert data['status']=='measured' and data['terminal_state']=='completed'
    assert data['input_bytes']==source.stat().st_size and data['input_integrity_unchanged']
    assert data['original_stats_bytes']>0 and data['waited_child_cpu_seconds']>0
    assert not data['derived_outputs'] and not data['unpublished_fastqs']
    assert [s['tool'] for s in data['execution_stages']]==['bcftools',*(['multiqc'] if multiqc else [])]
    assert all(s['resources']['elapsed_seconds']>0 for s in data['execution_stages'])
    assert data['qc_options']=={'per_sample':True,'multiqc':multiqc}
    evidence=ROOT/'validation/variant-qualification/benchmarks';evidence.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(output/'benchmark.json',evidence/('multiqc.json' if multiqc else 'native.json'))
