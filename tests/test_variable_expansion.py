import unittest

from builderer import Condition, Optional, Switch, Case
from builderer.details.variable_expansion import (
    resolve_conditionals,
    resolve_variables,
    bake_config,
)

from factories import make_config


class TestResolveConditionals(unittest.TestCase):
    def test_resolve_conditionals_selects_sources_for_the_active_platform(self):
        # one Optional per platform: exactly the active platform's source survives,
        # exercising both the "matched -> expand" and "unmatched -> drop" paths at once
        for platform, expected in [
            ("windows", "win.cpp"),
            ("linux", "linux.cpp"),
            ("macos", "mac.mm"),
        ]:
            with self.subTest(platform=platform):
                srcs = [
                    "common.cpp",
                    Optional(Condition(platform="windows"), "win.cpp"),
                    Optional(Condition(platform="linux"), "linux.cpp"),
                    Optional(Condition(platform="macos"), "mac.mm"),
                ]
                self.assertEqual(
                    resolve_conditionals(make_config(platform=platform), srcs),
                    ["common.cpp", expected],
                )

    def test_resolve_conditionals_recurses_into_nested_lists(self):
        cfg = make_config(toolchain="msvc")
        value = [["a", Optional(Condition(toolchain="msvc"), "b")]]
        self.assertEqual(resolve_conditionals(cfg, value), [["a", "b"]])

    def test_resolve_conditionals_bare_switch_resolves_to_single_value(self):
        cfg = make_config(toolchain="msvc")
        sw = Switch(Case(Condition(toolchain="msvc"), "/O2"))
        self.assertEqual(resolve_conditionals(cfg, sw), "/O2")


class TestResolveVariables(unittest.TestCase):
    def test_resolve_variables_substitutes_into_strings_and_lists(self):
        cfg = make_config()
        self.assertEqual(
            resolve_variables(cfg, {"name": "foo"}, "lib{name}.a"), "libfoo.a"
        )
        self.assertEqual(
            resolve_variables(cfg, {"x": "1"}, ["a{x}", "b{x}"]), ["a1", "b1"]
        )


class TestBakeConfig(unittest.TestCase):
    def test_bake_config_collapses_lists_to_the_chosen_scalars(self):
        cfg = make_config(
            architecture=["x64", "arm64"], build_config=["debug", "release"]
        )
        baked = bake_config(cfg, architecture="arm64", build_config="release")
        self.assertEqual((baked.architecture, baked.build_config), ("arm64", "release"))

    def test_bake_config_does_not_mutate_the_original(self):
        cfg = make_config(architecture=["x64"], build_config=["debug"])
        bake_config(cfg, architecture="x64", build_config="debug")
        self.assertEqual(cfg.architecture, ["x64"])
        self.assertEqual(cfg.build_config, ["debug"])

    def test_bake_config_rejects_values_not_present_in_the_config(self):
        cfg = make_config(architecture=["x64"], build_config=["debug"])
        with self.assertRaises(AssertionError):
            bake_config(cfg, architecture="ppc", build_config="debug")
        with self.assertRaises(AssertionError):
            bake_config(cfg, architecture="x64", build_config="profile")
