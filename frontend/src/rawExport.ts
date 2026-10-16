import type { Module } from "./types";

export type ExportMode = "verbatim" | "spreadsheet";
const numeric = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
/** Spreadsheet mode changes risky textual cells only; numeric lexemes stay exact.
 * A quoted leading tab follows OWASP's Excel-resistant mitigation. It is data,
 * so programmatic consumers must explicitly choose the verbatim scientific mode.
 */
export function exportModule<T extends Pick<Module, "columns" | "rows">>(
  module: T,
  delimiter: "," | "\t",
  mode: ExportMode = "verbatim",
): string {
  const field = (value: string) => {
    const risky =
      mode === "spreadsheet" &&
      !numeric.test(value) &&
      (/^[\s\p{Cc}\p{Cf}]*[=+\-@＝＋－＠]/u.test(value) ||
        /^[\p{Cc}\p{Cf}]/u.test(value));
    const text = risky ? "\t" + value : value;
    return risky || text.includes(delimiter) || /["\r\n]/.test(text)
      ? `"${text.replace(/"/g, '""')}"`
      : text;
  };
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
