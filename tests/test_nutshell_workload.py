#!/usr/bin/env python3
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NutShellWorkloadTests(unittest.TestCase):
    def test_design_reference_and_architecture_defaults(self):
        for design, expected in [('nutshell', 'riscv64-nutshell'), ('xiangshan', 'riscv64-xs')]:
            with self.subTest(design=design):
                result = subprocess.run(
                    ['make', '-s', '-C', str(ROOT), 'DESIGN=' + design,
                     '--eval=check-defaults:;@printf "%s %s\\n" "$(NEMU_CONFIG)" "$(AM_ARCH)"',
                     'check-defaults'], text=True, capture_output=True, check=True, timeout=30)
                self.assertIn(expected + '-ref_defconfig ' + expected, result.stdout)

    def test_hello_selects_only_requested_architecture(self):
        with tempfile.TemporaryDirectory(prefix='root-hello-test-') as temp:
            root = Path(temp)
            workload = root / 'workload'
            converter = root / 'converter'
            output = root / 'output'
            package = workload / 'build/am-workloads/hello/package/bin'
            package.mkdir(parents=True)
            converter.mkdir()
            (workload / 'Makefile').write_text('''am/hello:
	@test "$(ARCH)" = riscv64-nutshell
	@test "$(AM_ARCH)" = riscv64-nutshell
	@test "$(CPPFLAGS)" = '-DUART16550=1'
''')
            (package / 'hello-riscv64-nutshell.bin').write_bytes(b'nutshell hello')
            (package / 'hello-riscv64-xs.bin').write_bytes(b'incompatible xs hello')
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
            command = ['make', '-C', str(ROOT), 'workload', 'DESIGN=nutshell', 'TARGET=am/hello',
                       'JOBS=1', 'WORKLOAD_HOME=' + str(workload), 'BIN2DDR_HOME=' + str(converter),
                       'WORKLOAD_OUT_DIR=' + str(output), 'WORKLOAD_LOG=' + str(root / 'workload.log')]
            result = subprocess.run(command, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((output / 'nutshell-am-hello.bin').read_bytes(), b'nutshell hello')
            self.assertEqual((output / 'nutshell-am-hello.txt').read_bytes(), b'nutshell hello')
            (package / 'hello-riscv64-nutshell.bin').unlink()
            result = subprocess.run(command, text=True, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('workload binary not found', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
