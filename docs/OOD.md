# Open OnDemand 4.2 / OpenPBS integration

This adapter allocates resources through Batch Connect, then starts the ordinary standalone QualiDock process. It introduces no scheduler dependencies into the backend. Files, manifests, and reports must live on storage visible to compute nodes and persistent beyond the allocation.

## Required site settings

Configure the adapter for your HPC site's environment before use. An administrator must:

1. Set `cluster` in `deploy/ood/form.yml` to the actual OOD cluster ID from `/etc/ood/config/clusters.d`.
2. Set a valid PBS queue and optional account. Submission rejects the placeholder queue and invalid scheduler tokens.
3. Install QualiDock in a shared directory with a Python virtual environment, `pip install -e .`, and built `frontend/dist`. Set the installation path default accordingly. Node is needed at build time, not on the compute node at runtime.
4. Configure the environment modules in `template/before.sh.erb` for Java, FastQC 0.12.1, and MultiQC 1.25+. The executable checks fail if either tool is missing.
5. Choose readable input roots and a private persistent output directory. Configure directory ownership/ACLs appropriately for the current researcher.
6. Confirm OOD allows the compute-node hostnames and selected ports in the `/node` reverse proxy, uses HTTPS, preserves the external `Host` header for same-origin checks, and passes SSE without response buffering or a short idle timeout.

Copy `deploy/ood` to a user development app directory (`~/ondemand/dev/qualidock`) or your site's system app location. Ensure `template/script.sh` and `template/after.sh` are executable. The existing site's OpenPBS cluster adapter performs submission; QualiDock itself never calls `qsub`.

## Connection and proxy behavior

The before hook selects a port, creates a session password, exports the CPU/memory allocation, and sets `/node/<host>/<port>` as the external prefix. The connection view places the credential in a URL fragment, which is not sent in HTTP request URLs. The application exchanges it for a Secure, HttpOnly, SameSite cookie scoped to this session's prefix.

The frontend builds with a relative Vite asset base and uses relative URLs for APIs, downloads, and EventSource. The server accepts both a retained `/node` prefix and a stripped upstream path. If your site uses `/rnode`, update both `QUALIDOCK_PREFIX` in the before hook and the link in `view.html.erb`. Do not run multiple Uvicorn workers. Each output directory has an exclusive lock.

The server binds to `0.0.0.0` on the compute node so OOD can reach it. The session token protects data and execution even if a user can reach the node directly. The static application shell contains no private data. Do not turn off authentication based only on OOD login.

The after hook waits for the server port before exposing the connection. `set +x` keeps credentials out of shell trace output, and `umask 077` protects new files. Protect Batch Connect staging/connection files as well; these are managed by OOD.

## HPC deployment acceptance procedure

Record cluster/queue/module versions and the PBS job ID, then:

- Launch through Batch Connect; verify correct compute node, CPU/memory bounds and successful token exchange.
- Browse paired FASTQ files by server path; confirm both mates and execute FastQC + MultiQC.
- Compare native quality means, medians, quartiles, and whiskers against the downloaded official FastQC data.
- Confirm all assets load under the real proxy prefix; verify `/api/events` remains connected and job updates arrive.
- Run FastQC-only and MultiQC-only using existing FastQC reports.
- Cancel a large job; confirm the entire QC process group stops on the node and subsequent queued jobs can proceed.
- Exercise malformed FASTQ and resource failures and inspect their logs and partial outputs.
- End and restart the OOD session with the same output directory. Confirm completed results survive and unfinished runs become interrupted.
- Repeat traversal, escaped-symlink, unauthenticated download, and shell-metacharacter filename checks.

Release v0.1.0 only after these checks and standalone Linux acceptance pass.

This template follows the official [OOD 4.2 rendering and lifecycle documentation](https://osc.github.io/ood-documentation/latest/how-tos/app-development/interactive/template.html), [connection/proxy contract](https://osc.github.io/ood-documentation/latest/how-tos/app-development/interactive/view.html), and [submission format](https://osc.github.io/ood-documentation/latest/reference/files/submit-yml-erb.html). Each deployment must supply its own cluster configuration.
