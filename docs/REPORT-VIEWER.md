# Isolated official report preview

The existing analysis **Reports** tab includes a selector for registered HTML
reports, preferring `multiqc/multiqc_report.html`. Users can switch to individual
FastQC reports, enlarge the frame to 90% of the viewport height, retry a failed
load, and download the unchanged original. All other artifacts retain their
existing download rows. There is no new navigation page or persistence format.

## HTTP and isolation boundary

`GET /api/report-preview?run_id=<id>&path=<registered-artifact>` streams the
original HTML using `FileResponse`, `text/html`, and inline disposition.
`HEAD` performs the same authentication, artifact membership, containment,
symlink, existence, and HTML checks without sending report bytes. The UI checks
HEAD before embedding because iframe `load` events cannot distinguish opaque
HTTP error documents. It handles loading, denied access, missing reports,
unsupported formats, network failures, a 30-second timeout, and retry. A successful
iframe load indicates document loading, not proof that every report script worked.

The source URL remains relative to the application's existing proxy prefix.
Existing session cookies, including Secure/HttpOnly/SameSite settings, authorize
the initial frame navigation. No credential is placed in a report URL. Both
prefix-retaining `/node` and prefix-stripping `/rnode` routes use the existing
middleware. The reverse proxy must preserve the public Host, as already required
by QualiDock's same-origin API checks. A scheme-less CSP host source follows the
public HTTP/HTTPS scheme even when TLS terminates at OOD.

The application's script, object, and frame-ancestor protections remain in
place. Only the exact public `/api/report-preview` path may be framed, rather
than permitting arbitrary same-origin pages. The report response has its own
CSP and `X-Frame-Options: SAMEORIGIN`. Other responses retain `DENY`.

Both the frame attribute and the response CSP enforce `sandbox allow-scripts`
without `allow-same-origin`. This gives report code an opaque origin, including
when someone navigates directly to the preview URL. Its CSP permits bundled
inline scripts/styles and evaluated code needed by plotting libraries, data/blob
images and data fonts. It denies network connections, external scripts/styles,
forms, nested frames, objects and base URL changes. Camera, microphone, location,
payment, USB and fullscreen permissions are denied. There is no report message
handler or HTML insertion in the parent. API middleware also denies opaque
Origin and cross-site browser requests. Original attachment downloads retain
their prior binary content type, sandbox CSP and filename handling.

The design follows [MDN's iframe sandbox guidance](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe#sandbox)
and the [CSP specification](https://www.w3.org/TR/CSP/). The filesystem race
limitations in [SECURITY.md](SECURITY.md) still apply.

## Compatibility and deliberate restrictions

This is a restricted preview, **not a fully interactive MultiQC environment**.
In particular:

- MultiQC 1.35 attaches sample text filters and similar controls to native form
  submit events. The strict sandbox blocks those events before the handler runs,
  so those controls are unavailable. This follows the
  [HTML form submission algorithm](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#concept-form-submit).
  The viewer displays this limitation and keeps Download alongside the selector.
- Browser storage is unavailable, so MultiQC settings cannot persist. External
  services, including MultiQC's AI integrations, are blocked. Report-generated
  exports, clipboard/fullscreen operations and popup links may be unavailable.
- Official self-contained reports can use bundled JavaScript, CSS and data
  images. External/CDN resources and relative companion assets are not served
  through the preview. Custom templates or older imported HTML needing separate
  Images/JS/CSS directories may be incomplete. Use the original HTML and its
  associated report files/ZIP. QualiDock does not rewrite official reports or
  register additional files automatically just to make a preview work.
- No `allow-same-origin`, `allow-forms`, storage shim, injected compatibility
  script, or globally relaxed CSP is used. A separate report origin could permit
  additional controls, but requires an explicitly provisioned DNS/proxy origin,
  separate access credentials, and rejection of application cookies/APIs. It is
  not added to this single-server/OOD integration.

Native QC charts and raw-value tables remain the reliable application-native
view. Full MultiQC interaction is available by downloading the official HTML
and opening it outside the authenticated application.

## Tests and current evidence

Automated HTTP tests cover cookie and bearer access, GET/HEAD, unchanged HTML
bytes, inline vs attachment headers, restricted CSP, arbitrary/non-HTML paths,
traversal, file/directory/run symlinks, missing artifacts, unknown analyses,
HTTPS prefix-scoped cookies, retained and stripped prefixes, and restart history.
Real-tool tests also compare preview/download bytes from FastQC 0.13.0 and
MultiQC 1.35, including imported report companions and saved-result aggregation.
Frontend tests cover report selection, MultiQC preference, immutable records and
escaped paths under a proxy prefix.

The explicit browser suite uses actual installed FastQC 0.13.0 and MultiQC 1.35,
the production React build, and one ordinary-user FastAPI server. It covers
FastQC-only, combined, imported and aggregated runs, restart, report selection,
image/Plotly rendering, navigation, controls, the documented form restriction,
unchanged downloads, narrow layout, and malicious HTML attempting to read
parent DOM, cookies, storage and private API responses. Its malicious artifact
is solely a security probe; all scientific reports come from the real tools.

```sh
python -m pip install -e '.[test]' 'multiqc==1.35' 'playwright>=1.49,<2'
python -m playwright install chromium firefox
npm ci --prefix frontend
npm run build --prefix frontend
QUALIDOCK_BROWSER=chromium pytest -q tests/browser
QUALIDOCK_BROWSER=firefox pytest -q tests/browser
```

FastQC 0.13.0 must be on PATH, or set `QUALIDOCK_FASTQC`. Set `QUALIDOCK_MULTIQC`
for an explicit MultiQC installation. Playwright is a validation dependency only;
it is not required by the deployed application. CI includes both browser targets.

During the initial implementation the managed macOS environment rejected loopback socket
binding and native browser window access. Thus HTTP/real-tool tests and the
production build were run locally: **125 backend tests passed** with the real
FastQC 0.13.0 / MultiQC 1.35 installations configured, **41 frontend tests passed**,
and the TypeScript/Vite build passed. All 12 module tables and existing secure
download links also passed server-render checks. At that handoff the new browser
suite had not been executed; the subsequent CI result is recorded below. Actual browser
interaction, sandbox enforcement, and HTTPS OOD site acceptance remain validation
gates. Safari/WebKit is not yet covered.

Subsequent CI at [`e46ca0d`](https://github.com/PhoenixEmik/QualiDock/actions/runs/38714868496)
did execute both browsers. All opaque-origin security cases passed, while six
report-rendering waits per browser failed. The tests now navigate to a specific
FastQC quality plot instead of the first global SVG, which may belong to a hidden
General Statistics violin plot. That selector change is pending another CI run;
full rendering acceptance is still not established. Phase 3A also adds explicit
[native QC browser coverage](NATIVE-FASTQC.md). No sandbox restriction was relaxed.

## Files changed

- `backend/qualidock/app.py`, `preview.py`: existing authentication and artifact
  validation reused by the isolated GET/HEAD endpoint and narrow CSP policies.
- `frontend/src/AnalysisDetail.tsx`, `ReportViewer.tsx`, `reports.ts`, `styles.css`:
  Reports-tab integration, selection, states, sizing and unchanged download links.
- `backend/tests/test_preview.py`, `test_real_tools.py`,
  `frontend/tests/reports.test.ts`, `tests/browser/test_report_viewer.py`:
  HTTP/security, genuine tools, selection/escaping and explicit browser acceptance.
- `.github/workflows/ci.yml`: Chromium and Firefox report acceptance jobs.
- `README.md`, `docs/SECURITY.md`, `docs/PHASE2.md`, `docs/REPORT-VIEWER.md`:
  behavior, security boundary, restrictions and evidence. No runtime dependency,
  persistence migration, source FASTQ change, or tool installation is required.
