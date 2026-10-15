from pathlib import Path
from qualidock.resources import cgroup_limits


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_nested_v2_uses_tightest_ancestor(tmp_path):
    root=tmp_path/'cgroup'; member=tmp_path/'membership'
    member.write_text('0::/user.slice/session/job\n')
    write(root/'cpu.max', 'max 100000'); write(root/'memory.max','max')
    write(root/'user.slice/cpu.max','200000 100000'); write(root/'user.slice/memory.max',str(2048*1024*1024))
    write(root/'user.slice/session/job/cpu.max','350000 100000'); write(root/'user.slice/session/job/memory.max',str(4096*1024*1024))
    assert cgroup_limits(root, member)=={'cpus':2,'memory_mb':2048}


def test_v1_and_namespaced_mount_fallback(tmp_path):
    root=tmp_path/'cgroup'; member=tmp_path/'membership'
    member.write_text('2:cpu,cpuacct:/job\n3:memory:/job\n')
    write(root/'cpu/job/cpu.cfs_quota_us','150000'); write(root/'cpu/job/cpu.cfs_period_us','100000')
    write(root/'memory/job/memory.limit_in_bytes',str(1024*1024*1024))
    assert cgroup_limits(root,member)=={'cpus':1,'memory_mb':1024}
    member.write_text('0::/path-not-visible-in-this-namespace\n')
    write(root/'cpu.max','100000 100000'); write(root/'memory.max',str(512*1024*1024))
    assert cgroup_limits(root,member)=={'cpus':1,'memory_mb':512}


def test_missing_malformed_and_escape_are_ignored(tmp_path):
    root=tmp_path/'cgroup'; member=tmp_path/'membership'
    member.write_text('0::/../../outside\nmalformed\n')
    write(root/'cpu.max','invalid'); write(root/'memory.max','max')
    assert cgroup_limits(root,member)=={'cpus':None,'memory_mb':None}
