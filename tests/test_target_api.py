import unittest

from builderer.details.targets.cc_binary import CCBinary


class TestTargetAPI(unittest.TestCase):
    def test_cc_binary_rejects_library_only_parameters(self):
        # docs: cc_binary supports the same parameters as cc_library EXCEPT
        # hdrs and public_*
        for param in ["hdrs", "public_defines", "public_includes"]:
            with self.subTest(param=param):
                with self.assertRaises(TypeError):
                    CCBinary(name="x", workspace_root="pkg", **{param: ["y"]})
