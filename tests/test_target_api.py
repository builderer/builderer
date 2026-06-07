import pytest

from builderer.details.targets.cc_binary import CCBinary


@pytest.mark.parametrize("param", ["hdrs", "public_defines", "public_includes"])
def test_cc_binary_rejects_library_only_parameters(param):
    # docs: cc_binary supports the same parameters as cc_library EXCEPT hdrs and public_*
    with pytest.raises(TypeError):
        CCBinary(name="x", workspace_root="pkg", **{param: ["y"]})
