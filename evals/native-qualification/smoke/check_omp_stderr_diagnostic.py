#!/usr/bin/env python3
"""Exercise bounded, sanitized OMP model stderr publication without a provider."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / 'tools'))
import check_omp_loader_preflight as driver

COMMAND = ['python3', '-I', '-S', '/runtime/native_runtime_bootstrap.py']
SECRET = 'synthetic-omp-launch-key-7f91'


class BrokenStderr:
    def read(self, _size):
        raise OSError('synthetic read failure')

    def close(self):
        pass


class BrokenProcess:
    stderr = BrokenStderr()

    def poll(self):
        return 1


class PopenAdapter:
    PIPE = subprocess.PIPE
    DEVNULL = subprocess.DEVNULL

    def __getattr__(self, name):
        return getattr(subprocess, name)

    def __init__(self, stderr, *, incomplete=False):
        self.output = stderr
        self.incomplete = incomplete

    def Popen(self, command, *args, **kwargs):
        if self.incomplete:
            return BrokenProcess()
        code = 'import sys;sys.stderr.buffer.write(sys.stdin.buffer.read())'
        with tempfile.TemporaryFile() as source:
            source.write(self.output)
            source.seek(0)
            return subprocess.Popen([sys.executable, '-c', code], stdin=source, *args, **kwargs)


def observe(stderr, *, incomplete=False):
    adapter = PopenAdapter(stderr, incomplete=incomplete)
    module = SimpleNamespace(subprocess=adapter)
    result = {}
    previous = os.environ.get('OPENAI_API_KEY')
    os.environ['OPENAI_API_KEY'] = SECRET
    try:
        with driver.observe_model_stderr(module, result):
            module.subprocess.Popen(COMMAND, stderr=subprocess.DEVNULL)
    finally:
        if previous is None:
            os.environ.pop('OPENAI_API_KEY', None)
        else:
            os.environ['OPENAI_API_KEY'] = previous
    return result


def main():
    clean = observe(b'model loader failed: synthetic missing library')
    row, = clean['omp_model_stderr_categories']
    assert row.get('diagnostic') == 'model loader failed: synthetic missing library', row
    assert row['complete'] and not row['truncated'] and row['bytes'] == 46, row

    oversized = observe(b'x' * 65537)
    row, = oversized['omp_model_stderr_categories']
    assert row['truncated'] and row['bytes'] == 65537, row
    assert row.get('diagnostic') == '[oversized diagnostic withheld]', row

    incomplete = observe(b'', incomplete=True)
    row, = incomplete['omp_model_stderr_categories']
    assert not row['complete'] and row.get('diagnostic') == '[incomplete diagnostic withheld]', row

    refused = observe(f'loader says {SECRET}'.encode())
    row, = refused['omp_model_stderr_categories']
    assert row.get('diagnostic') == '[diagnostic redacted]', row
    assert SECRET not in repr(row), row
    print('OMP stderr diagnostic self-check passed')


if __name__ == '__main__':
    main()
