"""Admission for heavy work only; browsing and cancellation remain available."""
import os
from pathlib import Path
import shutil
import sys
import tempfile

from .usage_guard import UsageDenied

ROOT = Path(__file__).resolve().parents[1]


class HostBusy(UsageDenied):
    retryable = False


def _limit(name, default):
    try: return max(64, int(os.getenv(name, str(default)))) * 1024 * 1024
    except ValueError: return default * 1024 * 1024


def available_memory():
    if sys.platform.startswith('linux'):
        try:
            values = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
            available = int(values['MemAvailable'].split()[0]) * 1024
            # A container's limit may be lower than the host's available RAM.
            paths = [Path('/sys/fs/cgroup')]
            try:
                group = next(line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::'))
                leaf = (paths[0] / group.lstrip('/')).resolve()
                if leaf.is_relative_to(paths[0]): paths = [leaf, *[p for p in leaf.parents if p.is_relative_to(paths[0])]]
            except (OSError, StopIteration, ValueError): pass
            for path in paths:
                try:
                    maximum = (path / 'memory.max').read_text().strip()
                    if maximum != 'max':
                        available = min(available, max(0, int(maximum) - int((path / 'memory.current').read_text())))
                except (OSError, ValueError): pass
            return available
        except (OSError, KeyError, ValueError): return None
    if sys.platform == 'win32':
        import ctypes
        class MemoryStatus(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(name, ctypes.c_ulonglong) for name in
                ('total', 'available', 'page_total', 'page_available', 'virtual_total', 'virtual_available', 'extended')]
        status = MemoryStatus(); status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)): return status.available
    return None


def pressure_message():
    memory = available_memory()
    if memory is not None and memory < _limit('HOST_MIN_AVAILABLE_MEMORY_MB', 256):
        return '服务正在处理其他题目，请稍后再开始。本次未开始生成，原题与已完成结果仍可查看。'
    try:
        if min(shutil.disk_usage(ROOT).free, shutil.disk_usage(tempfile.gettempdir()).free) < _limit('HOST_MIN_FREE_DISK_MB', 512):
            return '生成服务暂时繁忙，已暂停新任务；原题与已完成结果仍可查看，请稍后再试。'
    except OSError: pass
    return ''


def require_capacity():
    message = pressure_message()
    if message: raise HostBusy(message)


def require_emergency_capacity():
    memory = available_memory()
    if memory is not None and memory < _limit('HOST_EMERGENCY_AVAILABLE_MEMORY_MB', 96):
        raise HostBusy('当前计算已达到资源保护线，已停止本次生成；题目与已完成步骤保留，请稍后再试。')
