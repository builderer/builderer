"""Cross-cutting determinism guarantees, run under the full CPython/PyPy CI matrix
so dict-ordering or hash-seed differences across interpreters surface as failures.
"""

import unittest

from builderer.generators.msbuild.utils import make_guid
from builderer.details.plist_xml import plist_dict_to_xml_text


class TestDeterminism(unittest.TestCase):
    def test_make_guid_pinned(self):
        # locks the uuid5(NAMESPACE_X500, key) derivation -- a change here would
        # silently alter every project/solution GUID and break existing
        # checked-in solutions
        self.assertEqual(
            make_guid("builderer"), "{70FF88D3-B806-5F07-88F8-FA26703FAE2F}"
        )

    def test_plist_xml_is_independent_of_key_insertion_order(self):
        a = plist_dict_to_xml_text(
            {"CFBundleName": "D", "CFBundleVersion": "1", "X": "y"}
        )
        b = plist_dict_to_xml_text(
            {"X": "y", "CFBundleVersion": "1", "CFBundleName": "D"}
        )
        self.assertEqual(a, b)
