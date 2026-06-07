import pytest

from builderer.details.targets.apple_application import (
    _is_plist_value,
    validate_resolved_info_plist,
    AppleApplication,
)

from conftest import make_cc_library, make_package, make_workspace

# A minimal valid Info.plist for constructors that don't exercise plist content.
PLIST = {"CFBundleExecutable": "A", "CFBundleIdentifier": "org.test.A"}


def test_is_plist_value_accepts_nested_lists_and_dicts():
    assert _is_plist_value([1, "a", [True]])
    assert _is_plist_value({"k": [1, {"k2": "v"}]})


def test_validate_accepts_a_valid_nested_plist():
    # a resolved, plist-representable dict passes silently (no exception)
    validate_resolved_info_plist("T", {"k": [1, "s", {"nested": True}]})


def test_validate_rejects_non_dict_after_resolution():
    # validation runs post-resolution; anything that isn't a dict is rejected
    with pytest.raises(ValueError, match="resolve to a dict"):
        validate_resolved_info_plist("T", ["not", "a", "dict"])


def test_validate_rejects_non_string_keys():
    with pytest.raises(ValueError, match="keys must all be strings"):
        validate_resolved_info_plist("T", {1: "v"})


def test_validate_rejects_unsupported_value_and_names_the_target():
    with pytest.raises(ValueError, match=r"MyApp.*unsupported value types"):
        validate_resolved_info_plist("MyApp", {"k": object()})


def test_constructor_defensively_copies_info_plist():
    src = {"CFBundleName": "Demo"}
    app = AppleApplication(
        name="A", binary=":bin", workspace_root="pkg", info_plist=src
    )
    src["mutated"] = "y"
    assert app.info_plist == {"CFBundleName": "Demo"}  # not aliased to caller's dict


def test_constructor_requires_info_plist():
    # an app bundle is invalid without an Info.plist, so it is a required argument
    with pytest.raises(TypeError):
        AppleApplication(name="A", binary=":bin", workspace_root="pkg")


def test_constructor_rejects_non_dict_non_conditional_info_plist():
    with pytest.raises(ValueError, match="a dict or a conditional"):
        AppleApplication(
            name="A", binary=":bin", workspace_root="pkg", info_plist=["x"]
        )


def test_constructor_records_binary_as_a_dependency():
    app = AppleApplication(
        name="A", binary=":bin", workspace_root="pkg", info_plist=PLIST
    )
    assert app.deps == [":bin"]  # the wrapped binary is always a dependency


def test_resolve_binary_target_rejects_a_non_cc_binary():
    app = AppleApplication(
        name="A", binary=":lib", workspace_root="pkg", info_plist=PLIST
    )
    lib = make_cc_library("lib", workspace_root="pkg")
    pkg = make_package("pkg", [app, lib])
    ws = make_workspace([pkg])
    with pytest.raises(ValueError, match="cc_binary"):
        app.resolve_binary_target(ws, pkg)
