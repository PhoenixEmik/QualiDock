import { useEffect, useState } from "react";
import { api, bytes } from "./api";
import type { Config, OutputLocation } from "./types";
export default function OutputDirectory({
  config,
  value,
  change,
  busy,
}: {
  config: Config | null;
  value: string;
  change: (path: string) => void;
  busy: boolean;
}) {
  const [locations, setLocations] = useState<OutputLocation[]>(
      config?.output_locations || [],
    ),
    [error, setError] = useState(""),
    [checking, setChecking] = useState(false);
  useEffect(() => setLocations(config?.output_locations || []), [config]);
  const chosen = value || config?.default_output || "";
  const location = locations.find((l) => l.path === chosen);
  const refresh = async () => {
    setChecking(true);
    try {
      setLocations(await api<OutputLocation[]>("api/output-locations"));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setChecking(false);
    }
  };
  return (
    <section className="form-section" aria-label="Output directory">
      <div className="form-heading">
        <h2>Output directory</h2>
      </div>
      <label className="field-label" htmlFor="output-root">
        Persistent results location
      </label>
      <select
        id="output-root"
        className="wide-input"
        value={chosen}
        disabled={busy}
        onChange={(e) => change(e.target.value)}
      >
        {!locations.length && (
          <option value="">Default results directory</option>
        )}
        {locations.map((l) => (
          <option key={l.path} value={l.path}>
            {l.path}
            {l.default ? " (default)" : ""}
            {!l.available ? " — unavailable" : ""}
          </option>
        ))}
      </select>
      <p className="inline-note">
        Results are stored in a new, unique analysis directory beneath this
        location. Choose among configured output roots; subdirectories are not
        browsable in this phase.
      </p>
      <div className="analytics-actions">
        <span>
          {location?.free_bytes !== null && location?.free_bytes !== undefined
            ? `${bytes(location.free_bytes)} available`
            : ""}
        </span>
        <button
          className="button small"
          disabled={busy || checking}
          onClick={() => void refresh()}
        >
          {checking ? "Checking…" : "Check location"}
        </button>
      </div>
      {(error || location?.error) && (
        <p className="error" role="alert">
          {error || location?.error}
        </p>
      )}
      <p className="mono output-destination">
        {chosen || "Default results directory"}/&lt;new analysis ID&gt;
      </p>
    </section>
  );
}
