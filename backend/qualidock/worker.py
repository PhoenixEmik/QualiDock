"""Apply Linux CPU affinity before exec; keep this process in its own process group."""
import os
import signal
import subprocess
import sys
import time


def main():
    limit = os.environ.pop('QUALIDOCK_MAX_FILE_BYTES', None)
    if limit:
        import resource
        resource.setrlimit(resource.RLIMIT_FSIZE, (int(limit), int(limit)))
    cpus = int(sys.argv[1])
    if hasattr(os, "sched_setaffinity"):
        available = sorted(os.sched_getaffinity(0))
        os.sched_setaffinity(0, available[:cpus])
    server_pid = int(sys.argv[2])
    child = subprocess.Popen(sys.argv[3:])
    while child.poll() is None:
        # Even SIGKILL of the web server must not leave orphan QC processes.
        if os.getppid() != server_pid:
            os.killpg(os.getpgrp(), signal.SIGKILL)
        time.sleep(0.2)
    sys.exit(child.returncode)


if __name__ == "__main__":
    main()
