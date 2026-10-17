"""Original NanoPlot 1.48.0 TSV and strict QC-only configuration contract."""
import asyncio
from pathlib import Path
import pytest
from qualidock.nanoplot import stats
from qualidock.optional_qc import options
from qualidock.tools import detect_tool

FIXTURE = Path(__file__).parent/'fixtures/nanoplot-1.48.0/NanoStats.txt'
SOURCE = {'records_scanned': 20, 'bases_scanned': 26248}


def test_original_stats_keep_reported_precision_and_compound_fields():
    value = stats(FIXTURE, SOURCE)
    rows = dict(value['rows'])
    assert rows['mean_read_length'] == '1312.4'
    assert rows['number_of_bases'] == '26248.0'
    assert rows['mean_qual'] == '18.8'  # Not nanoq's mean 19.090294.
    assert rows['Reads >Q20:'] == '6 (30.0%) 0.0Mb'
    assert value['rows'] == [line.split('\t') for line in FIXTURE.read_text().splitlines()[1:]]


@pytest.mark.parametrize('old,new', [
    ('number_of_reads\t20', 'number_of_reads\t21'),
    ('26248.0', '26249.0'), ('mean_qual\t18.8', 'mean_qual\tNaN'),
    ('Metrics\tdataset', 'invented\theader'),
    ('n50\t1475.0', 'n50\t-1'),
    ('median_qual\t19.2', 'mean_qual\t19.2'),
    ('mean_qual\t18.8', 'absent_metric\t18.8'),
])
def test_invalid_stats_are_not_registered(tmp_path, old, new):
    path=tmp_path/'NanoStats.txt';path.write_text(FIXTURE.read_text().replace(old,new))
    with pytest.raises(ValueError): stats(path,SOURCE)


def test_bounded_regular_stats(tmp_path):
    path=tmp_path/'NanoStats.txt';path.write_text('x'*(128*1024+1))
    with pytest.raises(ValueError,match='128 KiB'):stats(path,SOURCE)
    path.unlink();path.symlink_to(FIXTURE.resolve())
    with pytest.raises(ValueError,match='regular'):stats(path,SOURCE)


@pytest.mark.parametrize('supplied',[{'downsample':100},{'fastq_rich':True},{'individual_plots':1},{'loglength':'true'},{'multiqc':True}])
def test_no_filtering_metadata_sources_or_unverified_options(supplied):
    with pytest.raises(ValueError): options('nanoplot',supplied)


def test_absence_is_optional_and_old_qc_works(client,setup):
    _,root=setup
    client.app.state.manager.settings.nanoplot='/missing/NanoPlot'
    assert not client.get('/api/config').json()['tools']['nanoplot']
    assert client.post('/api/runs',json={'mode':'nanoplot','paths':[str(next(root.glob('*.fastq')))]}).status_code==400
    assert client.post('/api/runs',json={'mode':'fastqc','paths':[str(next(root.glob('*.fastq')))]}).status_code==201
    assert not asyncio.run(detect_tool('nanoplot','/missing/NanoPlot'))['compatible']
