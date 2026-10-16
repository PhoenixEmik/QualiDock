import type { ExportMode } from "./rawExport";

export default function ExportModeSelect({
  value,
  change,
}: {
  value: ExportMode;
  change: (mode: ExportMode) => void;
}) {
  return (
    <label>
      Export format{" "}
      <select
        aria-label="Data export safety"
        value={value}
        onChange={(event) => change(event.target.value as ExportMode)}
      >
        <option value="spreadsheet">
          Spreadsheet-safe (escape text formulas)
        </option>
        <option value="verbatim">Verbatim scientific values</option>
      </select>
      <small>
        {value === "spreadsheet"
          ? "Risky text receives a quoted leading tab; numeric values stay unchanged."
          : "Exact source cells. Treat names as untrusted text when opening in a spreadsheet."}
      </small>
    </label>
  );
}
