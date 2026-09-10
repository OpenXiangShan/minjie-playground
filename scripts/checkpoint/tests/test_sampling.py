"""Sampling invariants and checkpoint interface checks; no simulator required."""

import gzip
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sampling import allocate_samples, inspect_bbv, read_labels, select_samples
from step_cluster import run_cluster_step, resume_sampling_options
from step_metadata import build_aggregated_json, cluster_weight
from generate_checkpoint import (detect_auto_resume_state,
                                 prepare_auto_resume_artifacts,
                                 restore_auto_resume_artifacts)


class SamplingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bbv = self.root / 'profiling/demo/simpoint_bbv.gz'
        self.bbv.parent.mkdir(parents=True)
        with gzip.open(self.bbv, 'wt') as handle:
            for point in range(12):
                handle.write(f'T:{1 + point // 4}:100\n')

    def test_allocation_caps_and_exact_budget(self):
        for sizes_tuple in itertools.product(range(1, 5), repeat=3):
            sizes = dict(enumerate(sizes_tuple))
            for budget in range(len(sizes), sum(sizes.values()) + 1):
                allocation = allocate_samples(sizes, budget)
                self.assertEqual(sum(allocation.values()), budget)
                for label in sizes:
                    self.assertLessEqual(allocation[label], sizes[label])
                    self.assertGreaterEqual(allocation[label], 1)
        self.assertEqual(allocate_samples({0: 1, 1: 2, 2: 97}, 90), {0: 1, 1: 2, 2: 87})
        for budget in (2, 101):
            with self.assertRaises(ValueError):
                allocate_samples({0: 1, 1: 2, 2: 97}, budget)

    def test_strata_mass_and_original_ids(self):
        groups = {2: [0], 7: [1, 2], 19: list(range(3, 20))}
        samples, strata = select_samples(groups, 8, 42)
        self.assertEqual(samples, select_samples(groups, 8, 42)[0])
        self.assertEqual(len(samples), 8)
        self.assertEqual(len({s['interval_id'] for s in samples}), 8)
        self.assertEqual([s['sample_id'] for s in samples], list(range(8)))
        for stratum in strata:
            selected = [s for s in samples if s['cluster_id'] == stratum['cluster_id']]
            self.assertAlmostEqual(math.fsum(s['weight'] for s in selected), stratum['num_intervals'] / 20)
            self.assertTrue(all(s['interval_id'] in groups[stratum['cluster_id']] for s in selected))
        # Census must reproduce a known population mean, including a slow tail.
        census, _ = select_samples(groups, 20, 9)
        values = [100] + [1] * 19
        estimate = sum(s['weight'] * values[s['interval_id']] for s in census)
        self.assertAlmostEqual(estimate, sum(values) / 20)

    def test_invalid_rows_are_not_silently_renumbered(self):
        self.assertEqual(inspect_bbv(self.bbv)[0], 12)
        for contents in ('', 'T:1:100\n\nT:2:100\n', 'T:1:0\n', 'T:1:-1\n'):
            with gzip.open(self.bbv, 'wt') as handle:
                handle.write(contents)
            with self.assertRaises(ValueError):
                inspect_bbv(self.bbv)
        labels = self.root / 'labels0'
        labels.write_text('2 0\n7 0.1\n')
        with self.assertRaises(ValueError):
            read_labels(labels, 12)
        self.assertEqual(read_labels(labels, 2), {2: [0], 7: [1]})

    def test_random_outputs_resume_and_no_overwrite(self):
        options = {'sampling_method': 'random', 'num_samples': 5, 'seed': 7}
        with patch.dict(os.environ, {}, clear=True):
            metadata = run_cluster_step(archive_root=str(self.root), workload='demo', sampling_options=options)
        output = self.root / 'cluster/demo'
        rows = (output / 'simpoints0').read_text().splitlines()
        weights = (output / 'weights0').read_text().splitlines()
        self.assertEqual(len(rows), 5)
        for point, weight in zip(rows, weights):
            self.assertEqual(point.split()[1], weight.split()[1])  # NEMU reads rows in lockstep.
            self.assertAlmostEqual(float(weight.split()[0]), 0.2)
        original = {name: (output / name).read_bytes() for name in ('simpoints0', 'weights0')}
        inherited = resume_sampling_options(str(self.root), 'demo', {}, None)
        self.assertEqual(inherited, metadata['options'])
        with self.assertRaises(ValueError):
            resume_sampling_options(str(self.root), 'demo', {'seed': 8}, None)
        with self.assertRaises(FileExistsError):
            run_cluster_step(archive_root=str(self.root), workload='demo', sampling_options=options)
        # Existing auto-resume may request only missing points; restore full weights afterward.
        first = rows[0].split()[0]
        checkpoint = self.root / 'checkpoint/demo' / first
        checkpoint.mkdir(parents=True)
        (checkpoint / 'test.zstd').touch()
        state = detect_auto_resume_state(str(self.root), 'demo')
        prepare_auto_resume_artifacts(str(self.root), 'demo', state)
        self.assertEqual(len((output / 'simpoints0').read_text().splitlines()), 4)
        restore_auto_resume_artifacts(str(self.root), 'demo')
        for name, contents in original.items():
            self.assertEqual((output / name).read_bytes(), contents)

    def test_stratified_accepts_real_label_format(self):
        def fake_simpoint(command, **kwargs):
            def output(flag):
                return Path(command[command.index(flag) + 1])
            output('-saveLabels').write_text('2 0\n' * 4 + '7 0.1\n' * 8)
            output('-saveSimpoints').write_text('0 2\n4 7\n')
            output('-saveSimpointWeights').write_text('0.333333 2\n0.666667 7\n')
            self.assertEqual(command[command.index('-maxK') + 1], '2')

        executable = self.root / 'nemu/resource/simpoint/simpoint_repo/bin/simpoint'
        executable.parent.mkdir(parents=True)
        executable.write_text('fixture')
        executable.chmod(0o755)
        with patch.dict(os.environ, {'NEMU_HOME': str(self.root / 'nemu')}), patch('step_cluster.subprocess.run', side_effect=fake_simpoint):
            metadata = run_cluster_step(
                archive_root=str(self.root), workload='demo', max_k=2,
                sampling_options={'sampling_method': 'bbv-stratified', 'num_samples': 6})
        self.assertEqual(metadata['actual_num_samples'], 6)
        self.assertEqual({s['cluster_id'] for s in metadata['samples']}, {2, 7})
        self.assertAlmostEqual(sum(s['weight'] for s in metadata['samples']), 1)
        self.assertTrue((self.root / 'cluster/demo/centroid_simpoints0').exists())

    def test_single_interval_needs_no_clustering(self):
        with gzip.open(self.bbv, 'wt') as handle:
            handle.write('T:1:100\n')
        for method in ('simpoint', 'bbv-stratified', 'random'):
            options = {'sampling_method': method}
            if method != 'simpoint':
                options['num_samples'] = 1
            with patch.dict(os.environ, {}, clear=True):
                metadata = run_cluster_step(
                    archive_root=str(self.root), workload='demo',
                    sampling_options=options, output_dir=str(self.root / method))
            self.assertEqual(metadata['actual_num_samples'], 1)
            self.assertEqual(metadata['samples'][0]['interval_id'], 0)
            self.assertEqual(metadata['samples'][0]['weight'], 1)

    def test_metadata_preserves_small_weights_and_random_sets(self):
        output = self.root / 'cluster/demo'
        output.mkdir(parents=True)
        (output / 'simpoints0').write_text('0 0\n1 1\n')
        (output / 'weights0').write_text('0.99999 0\n0.00001 1\n')
        self.assertEqual(len(cluster_weight(self.root / 'cluster', 'demo')), 1)  # Legacy behavior.
        (output / 'sampling.json').write_text('{}')
        points = cluster_weight(self.root / 'cluster', 'demo')
        self.assertEqual(len(points), 2)
        info = {'demo': {'insts': '200', 'points': points,
                         'sampling': {'sampling_method': 'bbv-stratified'}}}
        self.assertEqual(build_aggregated_json(info, 0.3)['demo']['points'], points)
        info['demo']['sampling']['sampling_method'] = 'simpoint'
        self.assertEqual(len(build_aggregated_json(info, 0.3)['demo']['points']), 1)

    def test_cluster_only_cli_leaves_source_archive_unchanged(self):
        binary = self.root / 'demo.bin'
        binary.touch()  # Cluster-only needs no DTB, runtime binary, or profiling logs.
        experiment = self.root / 'experiment'
        archive_base = self.root.parent
        environment = {**os.environ, 'CHECKPOINT_OUTPUT_BASE': str(archive_base)}
        environment.pop('NEMU_HOME', None)
        command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'generate_checkpoint.py'),
                   '--input-path', str(binary), '--archive-id', self.root.name,
                   '--cluster-only', '--cluster-output-root', str(experiment),
                   '--sampling-method', 'random', '--num-samples', '4']
        before = self.bbv.read_bytes()
        subprocess.run(command, env=environment, check=True, capture_output=True, text=True)
        self.assertTrue((experiment / 'demo/sampling.json').exists())
        self.assertFalse((self.root / 'checkpoint').exists())
        self.assertFalse((self.root / 'metadata').exists())
        self.assertEqual(self.bbv.read_bytes(), before)
        result = subprocess.run(command, env=environment, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
