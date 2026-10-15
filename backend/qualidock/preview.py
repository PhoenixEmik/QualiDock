"""Policies for official HTML reports; report code never shares the app origin."""
import re
from urllib.parse import quote


PREVIEW_PATH = "/api/report-preview"
APP_CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-src {frames}; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
# Inline scripts are required by the standalone reports. No network sources,
# storage access, forms, nested frames, popups, or top-level navigation are granted.
REPORT_CSP = "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'; frame-ancestors 'self'"


def application_csp(host: str, prefix: str) -> str:
    # A scheme-less host source inherits the browser's scheme, including HTTPS
    # terminated by OOD. Permit only the dedicated endpoint, not arbitrary frames.
    # Host is untrusted request input and must not introduce CSP directives.
    if re.fullmatch(r"(?:[a-zA-Z0-9.-]+|\[[0-9a-fA-F:]+\])(?::[0-9]{1,5})?", host):
        frames = host + quote(prefix + PREVIEW_PATH, safe="/")
    else:
        frames = "'none'"
    return APP_CSP.format(frames=frames)
