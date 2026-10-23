#!/usr/bin/env bash
# Test-only upstream environment. QualiDock never installs scientific tools.
set -euo pipefail
rna_tools="${RUNNER_TEMP:-/tmp}/qualidock-rna-tools"
mkdir -p "$rna_tools" validation/rna-tool-study
python -m venv "$rna_tools/venv"
"$rna_tools/venv/bin/python" -m pip install 'RSeQC==5.0.5' 'pysam==0.24.1'
"$rna_tools/venv/bin/python" -I -c "import ctypes,pysam,pysam.version; lib=ctypes.CDLL(pysam.libchtslib.__file__); lib.hts_version.restype=ctypes.c_char_p; actual=lib.hts_version().decode('ascii'); assert pysam.__version__ == '0.24.1' and pysam.version.__htslib_version__ == actual == '1.24'; print('pysam',pysam.__version__,'native HTSlib',actual); print(pysam.libchtslib.__file__)" > validation/rna-tool-study/htslib-version.txt
ldd "$("$rna_tools/venv/bin/python" -I -c 'import pysam; print(pysam.libchtslib.__file__)')" > validation/rna-tool-study/pysam-linkage.txt
"$rna_tools/venv/bin/python" -m pip freeze > validation/rna-tool-study/dependencies.txt
for operation in infer_experiment read_distribution geneBody_coverage; do
  "$rna_tools/venv/bin/$operation.py" --version > "validation/rna-tool-study/$operation.version.txt"
  "$rna_tools/venv/bin/$operation.py" --help > "validation/rna-tool-study/$operation.help.txt"
done
python scripts/prepare-rna-test.py --output "$rna_tools/fixture"
"$rna_tools/venv/bin/infer_experiment.py" -i "$rna_tools/fixture/input.bam" -r "$rna_tools/fixture/genes.bed12" -s 200000 -q 30 > validation/rna-tool-study/input.infer_experiment.txt 2> validation/rna-tool-study/input.infer_experiment.log
"$rna_tools/venv/bin/read_distribution.py" -i "$rna_tools/fixture/input.bam" -r "$rna_tools/fixture/genes.bed12" > validation/rna-tool-study/input.read_distribution.txt 2> validation/rna-tool-study/input.read_distribution.log
cp "$rna_tools/fixture/genes.bed12" "$rna_tools/fixture/input.sam" validation/rna-tool-study/
mkdir -p "$rna_tools/bin"
for operation in infer_experiment read_distribution geneBody_coverage; do
  ln -sf "$rna_tools/venv/bin/$operation.py" "$rna_tools/bin/$operation.py"
done
if [ -n "${GITHUB_PATH:-}" ]; then echo "$rna_tools/bin" >> "$GITHUB_PATH"; fi
