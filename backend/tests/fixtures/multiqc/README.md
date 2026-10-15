# Genuine MultiQC General Statistics fixtures

These small JSON files are value-preserving subsets of **actual** MultiQC output
from the bundled, public synthetic FastQC 0.13.0 reports. Only `config_version`,
`report_general_stats_headers`, and `report_general_stats_data` were retained.
Plots, HTML, timestamps, command-line paths, and unrelated runtime configuration
are excluded. No patient data or private filesystem paths are present.

- **1.25.1**: list-based sections.
- **1.35**: section-keyed object format that reproduced issue #1 with the old parser.

Provenance and input/output SHA-256 hashes are in each version's `provenance.json`.
Original generation and both combined/imported real-tool tests passed on Ubuntu
24.04 with FastQC 0.13.0 and Java 17:
[CI run 38699403039](https://github.com/PhoenixEmik/QualiDock/actions/runs/38699403039).

Reproduce in an isolated Linux environment with the chosen MultiQC version:

```sh
python scripts/capture-multiqc-fixture.py --output /tmp/qualidock-multiqc-fixture
```

The script records the exact version, command, and SHA-256 hashes and asserts two
distinct sample rows. It copies the actual General Statistics subtrees without
rounding, scaling, or supplying missing cells. Changes to upstream metadata may
alter a whole-file hash; scientific values must still match the original report.

Normal parser regression tests require no installed QC tools. CI additionally
runs fixed 1.25.1 and 1.35 targets and a floating latest-supported `>=1.25,<2`
compatibility target. Updating a fixture requires a real run and new provenance;
never edit its reported values to make tests pass.
