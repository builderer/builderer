import unittest

from builderer import Condition, Optional, Switch, Case

from factories import make_config


class TestCondition(unittest.TestCase):
    def test_condition_scalar_match(self):
        cfg = make_config(toolchain="msvc")
        self.assertIs(Condition(toolchain="msvc")(cfg), True)
        self.assertIs(Condition(toolchain="clang")(cfg), False)

    def test_condition_list_membership(self):
        cfg = make_config(toolchain="gcc")
        self.assertIs(Condition(toolchain=["clang", "gcc"])(cfg), True)
        self.assertIs(Condition(toolchain=["clang", "msvc"])(cfg), False)

    def test_condition_missing_key_is_false(self):
        self.assertIs(Condition(nonexistent="x")(make_config()), False)

    def test_condition_requires_all_keys_to_match(self):
        cfg = make_config(toolchain="msvc", platform="windows")
        self.assertIs(Condition(toolchain="msvc", platform="windows")(cfg), True)
        self.assertIs(Condition(toolchain="msvc", platform="linux")(cfg), False)

    def test_condition_call_raises_on_list_valued_config(self):
        cfg = make_config(build_config=["debug", "release"])
        with self.assertRaisesRegex(ValueError, "cannot expand list"):
            Condition(build_config="debug")(cfg)

    def test_can_expand_is_false_only_when_matched_config_attr_is_a_list(self):
        cfg = make_config(toolchain="msvc", build_config=["debug", "release"])
        # scalar attr
        self.assertIs(Condition(toolchain="msvc").can_expand(cfg), True)
        # list attr
        self.assertIs(Condition(build_config="debug").can_expand(cfg), False)
        # unknown key ignored
        self.assertIs(Condition(unknown="x").can_expand(cfg), True)

    def test_empty_condition_always_matches(self):
        # Condition() is the documented "match any config" used for default/fallback
        # cases
        self.assertIs(Condition()(make_config(platform="linux")), True)

    def test_condition_matches_on_custom_config_field(self):
        # configs may carry arbitrary fields (e.g. profiler="tracy") for use in
        # conditions
        self.assertIs(Condition(profiler="tracy")(make_config(profiler="tracy")), True)
        self.assertIs(Condition(profiler="tracy")(make_config(profiler="none")), False)


class TestOptional(unittest.TestCase):
    def test_optional_expands_to_values_when_condition_holds(self):
        cfg = make_config(toolchain="msvc")
        opt = Optional(Condition(toolchain="msvc"), "/std:c++17", "/Zc:__cplusplus")
        self.assertEqual(list(opt(cfg)), ["/std:c++17", "/Zc:__cplusplus"])

    def test_optional_yields_nothing_when_condition_fails(self):
        cfg = make_config(toolchain="gcc")
        self.assertEqual(
            list(Optional(Condition(toolchain="msvc"), "/std:c++17")(cfg)), []
        )

    def test_optional_permissive_defers_itself_when_not_yet_expandable(self):
        cfg = make_config(build_config=["debug", "release"])
        opt = Optional(Condition(build_config="debug"), "-g")
        self.assertEqual(list(opt(cfg, permissive=True)), [opt])


class TestSwitch(unittest.TestCase):
    def test_switch_selects_first_matching_case(self):
        cfg = make_config(toolchain="msvc")
        sw = Switch(
            Case(Condition(toolchain="msvc"), "/O2"),
            Case(Condition(toolchain="gcc"), "-O2"),
        )
        self.assertEqual(list(sw(cfg)), ["/O2"])

    def test_switch_raises_when_no_case_matches(self):
        cfg = make_config(toolchain="clang")
        sw = Switch(Case(Condition(toolchain="msvc"), "/O2"))
        with self.assertRaisesRegex(RuntimeError, "no cases match config"):
            list(sw(cfg))

    def test_switch_permissive_defers_itself_when_not_yet_expandable(self):
        cfg = make_config(build_config=["debug", "release"])
        sw = Switch(Case(Condition(build_config="debug"), "-g"))
        self.assertEqual(list(sw(cfg, permissive=True)), [sw])

    def test_switch_falls_back_to_empty_condition_case(self):
        cfg = make_config(platform="linux")
        sw = Switch(
            Case(Condition(platform="windows"), "win"),
            Case(Condition(), "default"),  # documented fallback case
        )
        self.assertEqual(list(sw(cfg)), ["default"])
