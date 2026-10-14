from pathlib import Path
import sys
import pytest
from fastapi.testclient import TestClient
from qualidock.app import create_app
from qualidock.config import Settings
from qualidock.executor import LocalExecutor

NATIVE_MEMORY_SAMPLER = LocalExecutor.group_memory


@pytest.fixture(autouse=True)
def portable_monitor(monkeypatch):
    # The managed macOS sandbox denies ps. Production Linux uses /proc;
    # resource-limit reactions are exercised separately with deterministic readings.
    if sys.platform != "linux":
        async def memory(group):
            return 0
        monkeypatch.setattr(LocalExecutor, "group_memory", staticmethod(memory))


DATA = """##FastQC\t0.12.1
>>Basic Statistics\tpass
#Measure\tValue
Filename\t{filename}
File type\tConventional base calls
Encoding\tSanger / Illumina 1.9
Total Sequences\t1000
Sequence length\t150
%GC\t48
>>END_MODULE
>>Per base sequence quality\tpass
#Base\tMean\tMedian\tLower Quartile\tUpper Quartile\t10th Percentile\t90th Percentile
1\t32.5\t33\t30\t35\t28\t37
2-5\t34.2\t35\t32\t36\t30\t38
>>END_MODULE
>>Per sequence GC content\twarn
#GC Content\tCount
0\t0
48\t950
100\t0
>>END_MODULE
"""


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    for read in (1, 2):
        (root / f"sample_R{read}_001.fastq").write_text("@test\nACGT\n+\nIIII\n")
    tools = tmp_path / "tools"
    tools.mkdir()
    fastqc = tools / "fastqc"
    fastqc.write_text(f"#!{sys.executable}\n" + r'''import argparse, json, os, re, sys, time, zipfile
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--outdir');p.add_argument('--threads');p.add_argument('--memory');p.add_argument('--format');p.add_argument('files',nargs='+')
a=p.parse_args()
print('FastQC fixture: '+repr(a.files),flush=True)
if any('slow' in f for f in a.files): time.sleep(30)
failed=False
for file in a.files:
 path=Path(file)
 if 'broken' in file: failed=True;continue
 stem=re.sub(r'\.(fastq|fq)(\.gz)?$','',path.name)
 output=Path(a.outdir)/(stem+'_fastqc.zip')
 with zipfile.ZipFile(output,'w') as z: z.writestr(stem+'_fastqc/fastqc_data.txt',DATA.format(filename=path.name))
 (Path(a.outdir)/(stem+'_fastqc.html')).write_text('<html>official fixture</html>')
sys.exit(1 if failed else 0)
'''.replace("DATA.format", repr(DATA) + ".format"))
    multiqc = tools / "multiqc"
    multiqc.write_text(f"#!{sys.executable}\n" + '''import argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('scan');p.add_argument('--outdir');p.add_argument('--force',action='store_true');p.add_argument('--data-format');p.add_argument('--no-version-check',action='store_true')
a=p.parse_args();out=Path(a.outdir)
(out/'multiqc_report.html').write_text('<html>combined official fixture</html>')
(out/'multiqc_data').mkdir();(out/'multiqc_data/multiqc_data.json').write_text('{}')
print('MultiQC fixture completed',flush=True)
''')
    fastqc.chmod(0o700)
    multiqc.chmod(0o700)
    settings = Settings(roots=[root], output=tmp_path / "results", frontend=tmp_path / "frontend", token="test-session-secret", cpus=2, memory_mb=2048, fastqc=str(fastqc), multiqc=str(multiqc), allow_root=True)
    return settings, root


@pytest.fixture
def client(setup):
    settings, _ = setup
    with TestClient(create_app(settings)) as client:
        client.headers.update({"Authorization": f"Bearer {settings.token}", "X-QualiDock-Request": "1"})
        yield client
