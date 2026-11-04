"""Regression checks for the reference coverage-model cache."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from semconv_genai import conformance


class CoverageModelCacheTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.model = self.root / "model"
        self.source_dir = self.model / "gen-ai"
        self.source_dir.mkdir(parents=True)
        self.source = self.source_dir / "metrics.yaml"
        self.source.write_text("groups: []\n", encoding="utf-8")
        self.output = self.root / "coverage-model.json"
        self.output.write_text("{}", encoding="utf-8")
        for path in (self.model, self.source_dir, self.source):
            os.utime(path, (100, 100))
        os.utime(self.output, (200, 200))
        for name, value in (("MODEL_ROOT", self.model), ("SEMCONV_ROOT", self.root)):
            patcher = patch.object(conformance, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_deleted_source_rebuilds_cached_model(self):
        self.assertFalse(conformance._is_stale(self.output))
        self.source.unlink()
        os.utime(self.source_dir, (300, 300))

        def resolve(command, **kwargs):
            self.assertFalse(self.output.exists())
            self.assertEqual(command[-2:], [str(self.model), str(self.output)])
            self.output.write_text('{"metrics": {}}', encoding="utf-8")

        with (
            patch.object(conformance, "_uv", return_value="uv"),
            patch.object(conformance, "runner_project", return_value=self.root / "runner"),
            patch.object(conformance, "_environment", return_value={}),
            patch.object(conformance.subprocess, "run", side_effect=resolve) as run,
        ):
            self.assertEqual(conformance.coverage_model(self.output), self.output)
        run.assert_called_once()
        self.assertEqual(self.output.read_text(encoding="utf-8"), '{"metrics": {}}')

    def test_deleted_source_directory_is_stale(self):
        self.source.unlink()
        self.source_dir.rmdir()
        os.utime(self.model, (300, 300))
        self.assertTrue(conformance._is_stale(self.output))


if __name__ == "__main__":
    unittest.main()
