import tempfile
import unittest
from pathlib import Path

from builderer.details.glob_filter import glob_with_exclusions, split_patterns


class TestGlobFilter(unittest.TestCase):
    def test_split_patterns_separates_bang_prefixed_excludes(self):
        inc, exc = split_patterns(["*.cpp", "!*.test.cpp", "*.h"])
        self.assertEqual(inc, ["*.cpp", "*.h"])
        # leading '!' marks an exclude and is stripped
        self.assertEqual(exc, ["*.test.cpp"])

    def test_split_patterns_empty(self):
        self.assertEqual(split_patterns([]), ([], []))


class TestGlobWithExclusions(unittest.TestCase):
    def setUp(self):
        self._scratch = tempfile.TemporaryDirectory()
        self.root = Path(self._scratch.name)
        for rel in ["b/2.h", "b/1.h", "a/2.h", "a/1.h", "c/1.h"]:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")

    def tearDown(self):
        self._scratch.cleanup()

    def _glob(self, patterns):
        root = self.root.as_posix()
        return [
            Path(p).relative_to(root).as_posix()
            for p in glob_with_exclusions(self.root, patterns, Path.is_file)
        ]

    def test_results_follow_pattern_order_sorted_within_each_pattern(self):
        self.assertEqual(self._glob(["b/*.h", "a/1.h"]), ["b/1.h", "b/2.h", "a/1.h"])

    def test_duplicates_keep_first_position(self):
        self.assertEqual(self._glob(["a/2.h", "a/*.h"]), ["a/2.h", "a/1.h"])

    def test_excludes_apply(self):
        self.assertEqual(
            self._glob(["c/*.h", "**/*.h", "!a/*", "!**/2.h"]), ["c/1.h", "b/1.h"]
        )
