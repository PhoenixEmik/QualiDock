# Large-directory browsing

`FileAccess.browse` now builds a bounded, sorted **name index**, then reads
metadata only for the requested page and any confirmed mate outside that page.
It does not enumerate, resolve, and stat the whole directory for every page.
The first scan still costs O(number of names), and sorting costs O(n log n).
On filesystems without directory-entry type information, determining types can
require metadata I/O on that first scan. This is not claimed to be O(page size)
for a cold directory.

The shared index retains at most 200,000 names across up to eight directories,
evicting least recently used snapshots. A directory larger than 200,000 visible
entries returns a clear error asking for a smaller subdirectory. Snapshots expire
after five idle minutes. No database or filesystem watcher is required.

The API retains `offset`, `limit`, `entries`, and `total`, and adds:

- `snapshot`: an opaque listing-generation token; send it on subsequent pages.
- `next_offset`: the next position in the sorted index, or `null` at the end.
  This cursor advances even if an inaccessible entry is omitted.
- `refresh=true`: rebuild the initial listing explicitly.

Directory inode/device/mtime/ctime are checked at index creation and around each
page. A changed, evicted, or expired snapshot returns HTTP 409 instead of mixing
pages from different generations. Refresh retains the browser's input selection;
inputs are still revalidated when submitted and before execution. NFS attribute
caching can delay when remote changes become visible; use explicit refresh after
an external writer changes the tree.

Directory-first, case-insensitive name ordering is retained, with an exact-name
tiebreaker for deterministic pagination. Pair recognition uses the complete name
index, then rechecks the candidate mate's metadata and configured-root
containment. It never invents mates from the current page alone. Ambiguous pairs,
missing mates, lane suffixes and symlink restrictions remain supported.

Filesystem work runs off the API event loop. Search still covers loaded entries
locally and does not trigger a new server scan on each keystroke. The frontend
passes snapshot tokens and uses `next_offset`, including filtered empty pages.

## Local benchmark — 2026-10-15

A managed macOS/APFS temporary directory contained 100,000 synthetic empty file
names forming 50,000 FASTQ pairs. **No sequencing analysis was performed.** Two
500-entry pages were measured before and after, with Python `Path.stat` call
counting and tracemalloc enabled equally in both versions.

| Measurement | Previous implementation | Bounded name index |
|---|---:|---:|
| First page | 30.698 s | 2.179 s |
| Second page | 31.557 s | 0.032 s |
| Python Path.stat calls, first page | 500,001 | 504 |
| Python Path.stat calls, second page | 500,001 | 503 |
| Peak traced Python allocation | 109,586,993 bytes | 54,394,243 bytes |

These counts exclude metadata operations performed internally by directory-entry
APIs, and the times include instrumentation overhead. They are local regression
evidence, not NFS/Lustre latency guarantees or application-wide RSS measurements.
Actual shared-storage measurements remain part of site acceptance and issue #5.

Reproduce without touching production directories:

```sh
.venv/bin/python scripts/benchmark-browsing.py \
  --entries 100000 --pages 2 --output /tmp/qualidock-browsing.json
```

To compare an older implementation, supply `--baseline-file /path/to/old/files.py`.
The script creates and removes only its own temporary directory. Backend tests
also ensure warm pages never rescan, bound metadata reads to page/mate work,
exercise changes during browsing and cache eviction, and retain path and pairing
checks. Frontend tests cover token propagation, sparse pages, and stale snapshots.
