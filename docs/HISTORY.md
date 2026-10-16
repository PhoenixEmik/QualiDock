# Bounded history and live updates (#11)

The application now reads `GET /api/history` for a visible Analyses page only,
using server-side name/ID search, state/workflow filters and creation/completion
sorting. A page contains 25 summaries (API maximum 100), actual input counts,
states and timestamps; it excludes input paths, grouping, tool arguments, artifacts
and per-file outcome arrays. Missing completion dates sort last. The selected
analysis is fetched separately by immutable ID from `GET /api/runs/{id}`; filtering
or paging never changes its identity. Request generations discard stale responses.

`GET /api/events?format=invalidation` sends only `event: revision` with a revision
number. The browser refreshes its visible history page or selected full record.
Opening/reconnecting the SSE stream always sends an invalidation, including after
server restart; heartbeat comments do not trigger a refresh. SSE errors enable the
existing five-second polling fallback, and successful reconnection stops polling.
The frontend no longer retrieves all full manifests for browsing or live updates.

Compatibility is additive: `GET /api/runs` still returns full histories, and the
default `/api/events` retains legacy `runs` events for older clients. Those legacy
paths remain expensive by design during migration. Authentication, origin/CSRF
checks, URL prefixes and persistence/ownership locks apply unchanged. No database
or manifest migration was introduced. An optional `revision` query on `/api/history`
rejects changed snapshots with HTTP 409; the UI fetches a current window on refresh
and resets to page one when filters change. Out-of-range offsets are clamped.

## Measurement

A synthetic history test (300 records, 250 paths and pairing/outcome records each,
no scientific results) on the managed macOS development host measured three-request
median API time:

| Path | Body bytes | Median API time |
|---|---:|---:|
| Legacy full history | 26,765,591 | 1.075 s |
| 25-summary page | 7,844 | 0.00161 s |

SSE data JSON changed from 28,349,290 bytes to 17 bytes for a representative revision.
A separate local Node/V8 JSON decode measurement of the same history shape (seven iterations) were approximately 49.0 ms
versus 0.0163 ms; these are decoding proxies, **not browser rendering or shared
filesystem benchmarks**. Startup still scans configured run manifests, and history
sorting still visits in-memory records; this change bounds transmission/rendering,
not persistent-store startup complexity.

Reproduce the isolated API/payload measurement (requires existing test dependencies):

```sh
.venv/bin/python scripts/benchmark-history.py --runs 300 --inputs 250
```

The utility uses its own temporary store and refuses to replace an existing evidence
file. Timings depend on the environment. Browser acceptance additionally benchmarks
legacy/page request and JSON parse costs in the actual browser, checks 25-row
pagination, retained filters, selected details, forced SSE failure, polling updates
and reconnection. These use explicitly synthetic history metadata plus existing
genuine FastQC reports, never fabricated scientific metrics. CI publishes
`validation/history-browser*.json` alongside its existing browser artifacts.
