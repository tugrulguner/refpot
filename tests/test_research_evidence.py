"""Offline acceptance for the published, scoped research evidence."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / 'benchmarks/random-updates'


class ResearchEvidenceTests(unittest.TestCase):
    def test_recompute_exact_records_and_source_hashes(self):
        result = subprocess.run([sys.executable, str(EXPERIMENT / 'reproduce.py'), 'verify'],
                                check=True, capture_output=True, text=True)
        self.assertIn('exact 672 records', result.stdout)
        self.assertIn('all 16 service/setup/p99 cells', result.stdout)

    def test_failed_container_preserves_cause_before_copy(self):
        import importlib.util
        import os
        import tempfile
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('refpot_reproduce', EXPERIMENT / 'reproduce.py')
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as folder:
            output = Path(folder) / 'result'
            results = [subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 23)]
            with patch.object(module, 'fetch_sqlite'), patch.object(module.subprocess, 'run', side_effect=results) as run:
                with self.assertRaisesRegex(RuntimeError, 'container exited 23'):
                    module.execute('smoke', output)
            self.assertEqual(run.call_count, 2)
            self.assertFalse(any(call.args[0][:2] == ['docker', 'cp'] for call in run.call_args_list))
            self.assertEqual(json.loads((output / 'run.json').read_text())['exit_code'], 23)
            self.assertTrue((output / 'execution.log').is_file())

    def test_reopen_misses_remain_visible(self):
        recovery = json.loads((EXPERIMENT / 'recovery-comparison.json').read_text())
        self.assertEqual(len(recovery), 16)
        self.assertTrue(all(not r['native_faster'] for r in recovery))
        self.assertTrue(all(r['native_reopen_with_full_oracle_s'] >
                            r['best_SQL_reopen_with_full_oracle_s'] for r in recovery))
        readme = (EXPERIMENT / 'README.md').read_text()
        self.assertIn('slower for native in all 16 cells', readme)
        self.assertIn('not an ordinary update-only SQLite baseline', readme)
        self.assertIn('not physical power-loss validation', readme)

    def test_prior_misses_are_retained(self):
        prior = EXPERIMENT / 'prior-results'
        for experiment in ['value-concurrency-parent', 'value-sustained-parent']:
            records = json.loads((prior / experiment / 'summary.json').read_text())['summary']
            self.assertTrue(any(r['ratio_vs_best_same_policy_sql_service'] < 2 for r in records))

    def test_website_exports_are_synced(self):
        self.assertEqual((ROOT / 'README.md').read_bytes(),
                         (ROOT / 'website/public/docs/project-readme.md').read_bytes())
        for name in ['status', 'performance-method']:
            canonical = (ROOT / f'website/src/content/docs/{name}.md').read_text()
            exported = (ROOT / f'website/public/docs/{name}.md').read_text()
            import re
            self.assertEqual(re.sub(r'^---\r?\n[\s\S]*?\r?\n---\r?\n', '', canonical), exported)


if __name__ == '__main__':
    unittest.main()
