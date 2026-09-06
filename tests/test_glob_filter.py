import unittest

from builderer.details.glob_filter import split_patterns


class TestGlobFilter(unittest.TestCase):
    def test_split_patterns_separates_bang_prefixed_excludes(self):
        inc, exc = split_patterns(["*.cpp", "!*.test.cpp", "*.h"])
        self.assertEqual(inc, ["*.cpp", "*.h"])
        # leading '!' marks an exclude and is stripped
        self.assertEqual(exc, ["*.test.cpp"])

    def test_split_patterns_empty(self):
        self.assertEqual(split_patterns([]), ([], []))
