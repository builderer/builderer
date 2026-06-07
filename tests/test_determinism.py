"""Cross-cutting determinism guarantees, run under the full CPython/PyPy CI matrix
so dict-ordering or hash-seed differences across interpreters surface as failures.
"""

from builderer.generators.msbuild.utils import make_guid
from builderer.generators.make.target_mk import _plist_dict_to_xml_text


def test_make_guid_pinned():
    # locks the uuid5(NAMESPACE_X500, key) derivation -- a change here would silently
    # alter every project/solution GUID and break existing checked-in solutions
    assert make_guid("builderer") == "{70FF88D3-B806-5F07-88F8-FA26703FAE2F}"


def test_plist_xml_is_independent_of_key_insertion_order():
    a = _plist_dict_to_xml_text({"CFBundleName": "D", "CFBundleVersion": "1", "X": "y"})
    b = _plist_dict_to_xml_text({"X": "y", "CFBundleVersion": "1", "CFBundleName": "D"})
    assert a == b
