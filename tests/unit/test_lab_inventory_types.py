"""Pure inventory validation; no runtime or environment execution."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from engagement_lab_artifacts import validate_inventory
from engagement_controller import ControllerError


def inventory():
    paths = ['/', '/work', '/tmp', '/dev', '/dev/shm', '/dev/pts', '/dev/mqueue',
             '/proc', '/sys', '/sys/fs/cgroup', '/etc/hosts', '/etc/hostname', '/etc/resolv.conf']
    value = {'uid': 1, 'gid': 1, 'namespaces': {k: k + ':[123]' for k in
             ['ipc', 'pid', 'mnt', 'net', 'cgroup']}, 'mounts': []}
    for path in paths:
        row = dict(path=path, filesystem='overlay', readonly=True, writable=False,
                   size_bytes=0, mode=0o755, uid=0, gid=0,
                   kind='file' if path.startswith('/etc/') else 'directory', device=None)
        if path in ['/work', '/tmp', '/dev', '/dev/shm']:
            row.update(filesystem='tmpfs', readonly=False,
                       size_bytes=64*1024*1024 if path == '/dev' else 4096)
            if path in ['/work', '/tmp']:
                row.update(writable=True, uid=1, gid=1, mode=0o700)
            if path == '/dev/shm':
                row.update(writable=True, mode=0o1777)
        if path == '/dev/pts':
            row.update(filesystem='devpts')
        if path == '/dev/mqueue':
            row.update(filesystem='mqueue', readonly=False, writable=True, mode=0o1777)
        if path == '/proc':
            row.update(filesystem='proc')
        if path == '/sys':
            row.update(filesystem='sysfs')
        if path == '/sys/fs/cgroup':
            row.update(filesystem='cgroup2')
        value['mounts'].append(row)
    return value


class InventoryTypes(unittest.TestCase):
    def validate(self, value):
        return validate_inventory(value, {'uid': 1, 'gid': 1},
                                  {'workspace_bytes': 4096, 'memory_bytes': 100000000, 'pids': 32})

    def test_valid_inventory(self):
        value = inventory()
        before = copy.deepcopy(value)
        self.validate(value)
        self.assertEqual(value, before)

    def test_invalid_identity(self):
        for field in ('uid', 'gid'):
            for bad in (True, False, 1.0, '1', None, [], {}, 2):
                with self.subTest(field=field, value=bad):
                    value = inventory()
                    value[field] = bad
                    with self.assertRaisesRegex(ControllerError, 'lab_artifact_storage_unverified'):
                        self.validate(value)

    def test_invalid_namespace_shape(self):
        keys = list(inventory()['namespaces'])
        for bad in (keys, tuple(keys), None, True, 1, 'ipc', {}, {'ipc': 'ipc:[123]'}):
            with self.subTest(value=bad):
                value = inventory()
                value['namespaces'] = bad
                with self.assertRaisesRegex(ControllerError, 'lab_artifact_storage_unverified'):
                    self.validate(value)

if __name__ == '__main__':
    unittest.main()
