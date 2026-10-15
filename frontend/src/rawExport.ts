import type { Module } from "./types";

/** RFC-style quoting also protects TSV delimiters/newlines. No numeric conversion,
 * formula rewriting, rounding, comment injection, or zero substitution occurs.
 */
export function exportModule(module: Module, delimiter: "," | "\t"): string {
  const field = (value: string) =>
    value.includes(delimiter) || /["\r\n]/.test(value)
      ? `"${value.replace(/"/g, '""')}"`
      : value;
  return (
    [module.columns, ...module.rows]
      .map((row) => row.map(field).join(delimiter))
      .join("\r\n") + "\r\n"
  );
}

export function exportFilename(
  sampleName: string,
  moduleName: string,
  extension: "csv" | "tsv",
) {
  return (
    `${sampleName}-${moduleName}`.replace(/[^a-zA-Z0-9._-]+/g, "_") +
    `.${extension}`
  );
}
