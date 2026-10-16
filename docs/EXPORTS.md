# Scientific and spreadsheet exports

Raw FastQC Data, MultiQC General Statistics and comparison source CSV/TSV exports
provide an explicit **Export format** selector. The default UI choice is
**Spreadsheet-safe**. It prefixes potentially executable text (including formula
prefixes after whitespace/control/format characters and full-width variants) with
a tab inside a quoted field. CSV/TSV delimiters, quotes and multiline cells remain
escaped. Exact ASCII numeric lexemes, including negatives, exponent notation,
zero and reported precision, are not converted or rounded. Empty values stay empty.

**Verbatim scientific values** retains every original cell exactly and should be
used for scripts, statistical software and reproducibility. Sample names and other
text in this mode can be interpreted as formulas by spreadsheet software; import
those columns as text. The safe mode intentionally changes risky exported text,
not persisted metrics, chart values, tables or official report attachments.

This follows [OWASP's CSV injection guidance](https://community.owasp.org/attacks/CSV_Injection).
There is no universal CSV protection for every spreadsheet or import workflow.
The leading tab remains part of the exported data; spreadsheet re-saving or manual
editing may remove protections. Use the original safe export for spreadsheet
viewing, and use verbatim exports for machine consumption. No CSV export asserts
that arbitrary imported content is trustworthy. File extensions and scientific
units are unchanged by the selector.
