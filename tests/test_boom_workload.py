from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BoomWorkloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='boom-workload-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copyfile(ROOT / 'Makefile', self.root / 'Makefile')
        self.builder = self.root / 'workload-builder'
        self.builder.mkdir()
        (self.builder / 'Makefile').write_text('''linux/hello:
	@echo $(DEFAULT_DTB) > ../workload.args
''')
        firmware = self.builder / 'build/linux-workloads/hello'
        (firmware / 'dt').mkdir(parents=True)
        self.payload = b'firmware with its own embedded DTB'
        (firmware / 'fw_payload.bin').write_bytes(self.payload)
        (firmware / 'dt/boom-fpga-mem2g.dtb').write_bytes(b'must not be spliced')
        converter = self.root / 'Bin2ddr'
        converter.mkdir()
        (converter / 'Makefile').write_text('all:\n\t@:\n')
        binary = converter / 'bin2ddr'
        binary.write_text('''#!/usr/bin/env python3
import argparse
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('-i')
p.add_argument('-o')
a = p.parse_args()
Path(a.o).write_bytes(Path(a.i).read_bytes())
''')
        binary.chmod(0o755)

    def make(self, *args):
        return subprocess.run(['make', '--no-print-directory', '-s', 'workload', 'boom', *args],
                              cwd=self.root, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=30)

    def test_fpga_profile_and_firmware_are_preserved(self):
        result = self.make()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((self.root / 'workload.args').read_text().strip(), 'boom-fpga-mem2g')
        for suffix in ['bin', 'txt']:
            output = self.root / 'ready-to-run/boom-linux-hello' / ('boom-linux-hello.' + suffix)
            self.assertEqual(output.read_bytes(), self.payload)

    def test_custom_profile_and_am_rejection(self):
        result = self.make('WORKLOAD_DTB=custom-boom.dtb')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((self.root / 'workload.args').read_text().strip(), 'custom-boom')
        result = self.make('TARGET=am/hello')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('TARGET=linux/', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
