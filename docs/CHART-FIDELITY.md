# Application colors and FastQC chart fidelity

The application uses neutral slate surfaces and blue actions. Scientific colors
are independent: CSS variables in `frontend/src/styles.css` do not recolor plots.
The logo, typography, compact layout, navigation, reports and execution flow remain.
No dependency, backend API or persistence change is required.

## Application palette

| Purpose                          | Color                             |
| -------------------------------- | --------------------------------- |
| Background / sidebar / surface   | `#F7F8FA` / `#F1F3F6` / `#FFFFFF` |
| Muted surface / hover            | `#F5F6F8` / `#EEF1F5`             |
| Text / secondary text            | `#1F2937` / `#596579`             |
| Border / stronger border         | `#E2E5E9` / `#C5CCD6`             |
| Action / hover                   | `#315D8F` / `#264B74`             |
| Selection / selection hover      | `#EAF1FA` / `#E0EAFA`             |
| Success text / background        | `#15743A` / `#EDF8F0`             |
| Warning text / background        | `#925400` / `#FFF5DF`             |
| Error text / background          | `#B42318` / `#FFF0EE`             |
| Logs and toast background / text | `#202A39` / `#E7ECF3`             |

Success, warning and error text are darker than the starting palette to maintain
AA text contrast on their tinted backgrounds. Tests verify at least 4.5:1 for the
normal text/accent/status combinations. Focus and selection use blue; green is
retained for success and the original logo. This is a light theme, without a
theme switcher.

## Scientific palette and geometry

The reusable palette lives in `frontend/src/fastqcTheme.ts`.

| Meaning                                      | Color                                                                                  |
| -------------------------------------------- | -------------------------------------------------------------------------------------- |
| Quality regions: Q0–20 / Q20–28 / Q28+       | `#F9DEDE` / `#FFF0C9` / `#DDF2DF`                                                      |
| Interquartile box / median / whiskers / mean | `#F0F000` / `#C80000` / `#333333` / `#0000C8`                                          |
| A / C / G / T                                | `#2CA02C` / `#1F77B4` / `#444444` / `#D62728`                                          |
| Observed GC / supplied theoretical GC        | `#D62728` / `#1F77B4`                                                                  |
| Paired quality: R1 / R2                      | `#1F77B4` / `#D97706`                                                                  |
| General profiles (Tol)                       | `#882255`, `#332288`, `#117733`, `#DDCC77`, `#44AA99`, `#AA4499`, `#CC6677`, `#88CCEE` |
| Tile scale: decrease toward no decrease      | red → yellow → green → cyan → blue                                                     |

`qualityPlot.ts` draws an independent horizontal median segment inside each box.
Its input remains the reported p10, lower quartile, median, upper quartile and p90,
in the existing order. Missing quantiles omit the incomplete box, without changing
other reported values or inventing replacements. The blue mean is a separate line.
Exact original row strings remain in tooltips and Raw Data.

A silent `markArea` layer spans 0–20, 20–28 and 28 to the actual numeric upper
limit. It remains visible when statistical series are hidden and follows the
axis during zoom and resize. These regions are visual guides, **not** the
configurable module PASS/WARN/FAIL rules. Official classifications are unchanged.

Paired quality uses blue/orange curves and the same quality regions. Base, GC and
adapter identities retain their colors across reads; R1 is solid/circle and R2 is
dashed/triangle. Existing accessible series checkboxes and scrollable legends remain.
Only genuinely compatible bins/columns are overlaid; missing values remain gaps.

Sequence-quality and sequence-length distributions use FastQC-style connected
count lines, with a marker for a single point. Base composition, N content and
adapter percentages retain the official 0–100% axis. Other distributions keep
unscaled reported values. Quality bands are not added to count or percentage axes.

Tile cells retain the original signed mean Phred deviations. Negative deviations
progress from blue to warmer colors as they decrease. Zero and positive values
are blue, following FastQC's no-decrease convention. The displayed domain uses
the observed negative minimum, with at least a one-Phred span to avoid amplifying
tiny deviations. It is a visualization scale, not a reconstruction of the original
configured failure threshold or FastQC's nonlinear gradient.

## References and deliberate differences

- Quality geometry follows the [official module help](https://www.bioinformatics.babraham.ac.uk/projects/fastqc/Help/3%20Analysis%20Modules/2%20Per%20Base%20Sequence%20Quality.html).
- The actual FastQC 0.13.0 SVG figures from the existing fixture ZIPs were compared
  side by side in Firefox. Their `fastqc_data.txt` files match the committed golden
  fixtures byte for byte. No original HTML, ZIP or scientific fixture was modified.
- Native plots keep lighter quality bands, neutral grids, interactive legends and
  zoom controls. Alternating background stripes are omitted. The existing native
  quality scale starts at 0 with an upper bound of at least 45, expanded to include
  both reads' reported statistics; official reports can use different bounds/ticks.
- FastQC 0.13.0 uses Tol colors for general line graphs. Nucleotide and GC colors
  deliberately follow the classic identities requested here, so they do not match
  every 0.13.0 SVG pixel/color.
- FastQC's genuine GC data table contains observed counts only. Its theoretical
  curve exists in the official report but is not exported in that table. Native
  plots explicitly identify the missing reference and do not calculate it. If a
  saved module supplies a theoretical column, that series is blue and retains its
  original data. Pair comparison still uses shared columns only.
- K-mer output provides maximum observed/expected enrichment and its position,
  rather than a complete per-position enrichment curve. The existing maximum
  enrichment bars and full raw table remain; no positional curve is fabricated.

This is a visual and numerical fidelity review, not pixel-perfect equivalence.

## Validation

- Backend: **133 passed**, including real FastQC 0.13.0 / MultiQC 1.35, saved
  results, path validation and existing preview/download security.
- Frontend: **95 passed**. New checks cover custom glyph geometry, exact fixture
  statistics, missing quantiles, independent bands, quality/read/nucleotide/GC
  colors, percentage axes, genuine tile data, resize/zoom SVG rendering at 350 and
  1000 pixels, and application text contrast. Existing pairing, raw export,
  module navigation and report-link checks remain.
- TypeScript/Vite production build passed. The existing large ECharts bundle
  warning remains; no new library was introduced.
- Firefox manual checks used both a genuine-fixture component comparison and the
  already-running authenticated application at `127.0.0.1:8765`. Workspace,
  persisted analysis loading, paired quality curves, series visibility, medians
  and the live 390px responsive chart/legend were inspected without rerunning QC.

Captured browser PNGs are local validation artifacts (excluded from Git):

- `validation/fastqc-fidelity/workspace-neutral.png`
- `validation/fastqc-fidelity/quality-R1-comparison.png`
- `validation/fastqc-fidelity/quality-R2-comparison.png`
- `validation/fastqc-fidelity/content-R1-comparison.png`
- `validation/fastqc-fidelity/GC-R1-comparison.png`
- `validation/fastqc-fidelity/live-paired-quality.png`

The automated Chromium/Firefox HTTP suite was not rerun locally: this managed
environment cannot start its own loopback test listener. The pre-change CI at
[`7619526`](https://github.com/PhoenixEmik/QualiDock/actions/runs/38762084625)
passed native-browser and isolation checks (9 cases per browser), but still failed
6 existing official-report rendering waits per browser. This visual task does not
change the report viewer, sandbox or those tests. A green report-browser suite and
HTTPS/OOD acceptance remain separate verification gates.

## Changed files

- `frontend/src/styles.css`: semantic application tokens and existing UI states.
- New `frontend/src/fastqcTheme.ts`, `qualityPlot.ts`: scientific palette and glyphs.
- `frontend/src/chartOptions.ts`, `comparisonChart.ts`: scientific styles, bands,
  percentile geometry, axes, legends and neutral chart controls.
- `frontend/src/QcModule.tsx`, `PairComparison.tsx`, `AnalysisDetail.tsx`: GC
  availability and statistical color guidance; comparison behavior is retained.
- `frontend/src/FileExplorer.tsx`: folder fill uses the neutral surface token.
- New `frontend/tests/chart-fidelity.test.ts`; updated `native-qc.test.ts` distinguishes
  the empty background layer from real statistical series while checking all data.
- README, this document and the native FastQC documentation link.
