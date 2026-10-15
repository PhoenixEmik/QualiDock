"""Policies for official HTML reports; report code never shares the app origin."""
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

from fastapi.responses import FileResponse, Response, StreamingResponse


PREVIEW_PATH = "/api/report-preview"
APP_CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-src {frames}; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
# Inline scripts are required by the standalone reports. No network sources,
# storage access, forms, nested frames, popups, or top-level navigation are granted.
REPORT_CSP = "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'; frame-ancestors 'self'"

# Some MultiQC versions read localStorage during bundle initialization without
# catching SecurityError. This facade is private to one opaque document, not
# browser storage. It never obtains a parent reference, credential or network API.
# The stored report and attachment download remain byte-for-byte original.
MEMORY_STORAGE_BOOTSTRAP = b'''<script data-qualidock-preview="memory-storage">
(() => {
  "use strict";
  // MultiQC's AI-cookie initialization also assumes a readable cookie API.
  // Supply no cookies and ignore writes; this never exposes browser cookies.
  try { void document.cookie; } catch (_) {
    Object.defineProperty(document, "cookie", { get: () => "", set: () => {} });
  }
  for (const name of ["localStorage", "sessionStorage"]) {
    try { void window[name]; continue; } catch (_) { /* Opaque sandbox. */ }
    const values = new Map();
    let size = 0;
    const storage = Object.create(null);
    Object.defineProperties(storage, {
      length: { get: () => values.size },
      key: { value: index => Array.from(values.keys())[Number(index) >>> 0] ?? null },
      getItem: { value: key => values.get(String(key)) ?? null },
      setItem: { value: (key, value) => {
        key = String(key); value = String(value);
        const previous = values.has(key) ? (key.length + values.get(key).length) * 2 : 0;
        const next = size - previous + (key.length + value.length) * 2;
        if (next > 2 * 1024 * 1024) throw new DOMException("Preview storage is full", "QuotaExceededError");
        values.set(key, value); size = next;
      } },
      removeItem: { value: key => {
        key = String(key);
        if (values.has(key)) { size -= (key.length + values.get(key).length) * 2; values.delete(key); }
      } },
      clear: { value: () => { values.clear(); size = 0; } },
    });
    Object.defineProperty(window, name, { value: Object.freeze(storage) });
  }
})();
</script>'''


class UnsupportedPreview(ValueError):
    pass


class _HeadPosition(HTMLParser):
    """Find a real head tag (not one inside a comment or script string)."""
    def __init__(self, prefix):
        super().__init__()
        self.lines = prefix.split("\n")
        self.head_end = None
        self.early_script = False

    def handle_starttag(self, tag, attrs):
        if tag == "script" and self.head_end is None:
            self.early_script = True
        if tag == "head" and self.head_end is None and not self.early_script:
            row, column = self.getpos()
            self.head_end = sum(len(line) + 1 for line in self.lines[:row - 1]) + column + len(self.get_starttag_text())


def report_preview(artifact: Path, *, multiqc: bool, head: bool = False):
    headers = {
        "Content-Security-Policy": REPORT_CSP,
        "X-Frame-Options": "SAMEORIGIN",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), fullscreen=()",
    }
    response = FileResponse(artifact, media_type="text/html", filename=artifact.name,
                            content_disposition_type="inline", headers=headers)
    if not multiqc:
        return response
    # Inspect a bounded prefix, then stream the original remainder. Large reports
    # are not loaded in full and no output file is rewritten or regenerated.
    with artifact.open("rb") as stream:
        prefix = stream.read(64 * 1024)
        size = stream.seek(0, 2)
    parser = _HeadPosition(prefix.decode("latin1"))  # One character per byte.
    parser.feed(prefix.decode("latin1"))
    if parser.head_end is None:
        raise UnsupportedPreview("The report has no supported HTML head; download the original report")
    offset = parser.head_end
    response.headers["Content-Length"] = str(size + len(MEMORY_STORAGE_BOOTSTRAP))
    response.headers["X-QualiDock-Preview-Compatibility"] = "memory-storage"
    if head:
        return Response(headers=dict(response.headers))

    def content():
        with artifact.open("rb") as stream:
            yield stream.read(offset)
            yield MEMORY_STORAGE_BOOTSTRAP
            while chunk := stream.read(64 * 1024):
                yield chunk
    return StreamingResponse(content(), headers=dict(response.headers))


def application_csp(host: str, prefix: str) -> str:
    # A scheme-less host source inherits the browser's scheme, including HTTPS
    # terminated by OOD. Permit only the dedicated endpoint, not arbitrary frames.
    # Host is untrusted request input and must not introduce CSP directives.
    if re.fullmatch(r"(?:[a-zA-Z0-9.-]+|\[[0-9a-fA-F:]+\])(?::[0-9]{1,5})?", host):
        frames = host + quote(prefix + PREVIEW_PATH, safe="/")
    else:
        frames = "'none'"
    return APP_CSP.format(frames=frames)
