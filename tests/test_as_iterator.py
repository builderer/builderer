import unittest

from builderer.details.as_iterator import str_iter, str_scalar


class TestAsIterator(unittest.TestCase):
    def test_str_iter_normalizes_scalar_and_collections(self):
        self.assertEqual(list(str_iter("a")), ["a"])
        self.assertEqual(list(str_iter(["a", "b"])), ["a", "b"])
        self.assertEqual(list(str_iter({"a"})), ["a"])

    def test_str_scalar_unwraps_single_value(self):
        self.assertEqual(str_scalar("a"), "a")
        self.assertEqual(str_scalar(["a"]), "a")

    def test_str_scalar_rejects_ambiguous_input(self):
        # a scalar is expected, so 0 or >1 elements must fail loudly rather than guess
        with self.assertRaises(ValueError):
            str_scalar(["a", "b"])
        with self.assertRaises(ValueError):
            str_scalar([])
