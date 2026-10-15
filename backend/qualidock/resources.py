"""Read this process's standard Linux cgroup hierarchy, including ancestor limits."""
from pathlib import Path


def cgroup_limits(root=Path('/sys/fs/cgroup'), membership=Path('/proc/self/cgroup')) -> dict:
    cpus, memory = [], []
    paths = [(root, 'v2'), (root / 'cpu', 'cpu'), (root / 'cpu,cpuacct', 'cpu'), (root / 'memory', 'memory')]
    try:
        lines = membership.read_text().splitlines()
    except OSError:
        lines = []
    for line in lines:
        fields = line.split(':', 2)
        if len(fields) != 3 or '..' in Path(fields[2]).parts:
            continue
        controllers, relative = fields[1].split(','), fields[2].lstrip('/')
        bases = [(root, 'v2')] if fields[0] == '0' and fields[1] == '' else [(root / 'cpu', 'cpu'), (root / 'cpu,cpuacct', 'cpu')] if 'cpu' in controllers else []
        if 'memory' in controllers:
            bases.append((root / 'memory', 'memory'))
        for base, kind in bases:
            path = base / relative
            while path.is_relative_to(base):
                paths.append((path, kind))
                if path == base:
                    break
                path = path.parent
    for path, kind in dict.fromkeys(paths):
        try:
            if kind == 'v2':
                quota, period = (path / 'cpu.max').read_text().split()
            elif kind == 'cpu':
                quota, period = (path / 'cpu.cfs_quota_us').read_text(), (path / 'cpu.cfs_period_us').read_text()
            else:
                quota, period = '-1', '1'
            if quota.strip() != 'max' and int(quota) > 0 and int(period) > 0:
                cpus.append(max(1, int(quota) // int(period)))
        except (OSError, ValueError):
            pass
        if kind in {'v2', 'memory'}:
            try:
                value = (path / ('memory.max' if kind == 'v2' else 'memory.limit_in_bytes')).read_text().strip()
                if value != 'max' and int(value) > 0:
                    memory.append(max(1, int(value) // (1024 * 1024)))
            except (OSError, ValueError):
                pass
    return {'cpus': min(cpus) if cpus else None, 'memory_mb': min(memory) if memory else None}
