import unittest
from typing import Any

from builderer.details.targets.apple_application import (
    _is_plist_value,
    validate_resolved_info_plist,
    AppleApplication,
)

from factories import make_cc_library, make_package, make_workspace

# A minimal valid Info.plist for constructors that don't exercise plist content.
PLIST = {"CFBundleExecutable": "A", "CFBundleIdentifier": "org.test.A"}


class TestInfoPlistValidation(unittest.TestCase):
    def test_is_plist_value_accepts_nested_lists_and_dicts(self):
        self.assertTrue(_is_plist_value([1, "a", [True]]))
        self.assertTrue(_is_plist_value({"k": [1, {"k2": "v"}]}))

    def test_validate_accepts_a_valid_nested_plist(self):
        # a resolved, plist-representable dict passes silently (no exception)
        validate_resolved_info_plist("T", {"k": [1, "s", {"nested": True}]})

    def test_validate_rejects_non_dict_after_resolution(self):
        # validation runs post-resolution; anything that isn't a dict is rejected.
        # resolve_conditionals() produces dynamically-typed data, so the value
        # reaching the guard is genuinely Any -- model that here.
        resolved: Any = ["not", "a", "dict"]
        with self.assertRaisesRegex(ValueError, "resolve to a dict"):
            validate_resolved_info_plist("T", resolved)

    def test_validate_rejects_non_string_keys(self):
        with self.assertRaisesRegex(ValueError, "keys must all be strings"):
            validate_resolved_info_plist("T", {1: "v"})

    def test_validate_rejects_unsupported_value_and_names_the_target(self):
        with self.assertRaisesRegex(ValueError, r"MyApp.*unsupported value types"):
            validate_resolved_info_plist("MyApp", {"k": object()})


class TestAppleApplicationConstructor(unittest.TestCase):
    def test_constructor_defensively_copies_info_plist(self):
        src = {"CFBundleName": "Demo"}
        app = AppleApplication(
            name="A", binary=":bin", workspace_root="pkg", info_plist=src
        )
        src["mutated"] = "y"
        # not aliased to caller's dict
        self.assertEqual(app.info_plist, {"CFBundleName": "Demo"})

    def test_constructor_requires_info_plist(self):
        # an app bundle is invalid without an Info.plist, so it is a required
        # argument. Omitting it is only reachable from dynamically-typed code, so we
        # model that caller via an Any-typed reference to the constructor.
        constructor: Any = AppleApplication
        with self.assertRaises(TypeError):
            constructor(name="A", binary=":bin", workspace_root="pkg")

    def test_constructor_rejects_non_dict_non_conditional_info_plist(self):
        # neither a dict nor a ConditionalValue; only reachable dynamically
        bad_info_plist: Any = ["x"]
        with self.assertRaisesRegex(ValueError, "a dict or a conditional"):
            AppleApplication(
                name="A", binary=":bin", workspace_root="pkg", info_plist=bad_info_plist
            )

    def test_constructor_records_binary_as_a_dependency(self):
        app = AppleApplication(
            name="A", binary=":bin", workspace_root="pkg", info_plist=PLIST
        )
        # the wrapped binary is always a dependency
        self.assertEqual(app.deps, [":bin"])


class TestResolveBinaryTarget(unittest.TestCase):
    def test_resolve_binary_target_rejects_a_non_cc_binary(self):
        app = AppleApplication(
            name="A", binary=":lib", workspace_root="pkg", info_plist=PLIST
        )
        lib = make_cc_library("lib", workspace_root="pkg")
        pkg = make_package("pkg", [app, lib])
        ws = make_workspace([pkg])
        with self.assertRaisesRegex(ValueError, "cc_binary"):
            app.resolve_binary_target(ws, pkg)
