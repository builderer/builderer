import pytest

from builderer import Condition, Optional, Switch, Case

from conftest import make_config


def test_condition_scalar_match():
    cfg = make_config(toolchain="msvc")
    assert Condition(toolchain="msvc")(cfg) is True
    assert Condition(toolchain="clang")(cfg) is False


def test_condition_list_membership():
    cfg = make_config(toolchain="gcc")
    assert Condition(toolchain=["clang", "gcc"])(cfg) is True
    assert Condition(toolchain=["clang", "msvc"])(cfg) is False


def test_condition_missing_key_is_false():
    assert Condition(nonexistent="x")(make_config()) is False


def test_condition_requires_all_keys_to_match():
    cfg = make_config(toolchain="msvc", platform="windows")
    assert Condition(toolchain="msvc", platform="windows")(cfg) is True
    assert Condition(toolchain="msvc", platform="linux")(cfg) is False


def test_condition_call_raises_on_list_valued_config():
    cfg = make_config(build_config=["debug", "release"])
    with pytest.raises(ValueError, match="cannot expand list"):
        Condition(build_config="debug")(cfg)


def test_can_expand_is_false_only_when_matched_config_attr_is_a_list():
    cfg = make_config(toolchain="msvc", build_config=["debug", "release"])
    assert Condition(toolchain="msvc").can_expand(cfg) is True  # scalar attr
    assert Condition(build_config="debug").can_expand(cfg) is False  # list attr
    assert Condition(unknown="x").can_expand(cfg) is True  # unknown key ignored


def test_optional_expands_to_values_when_condition_holds():
    cfg = make_config(toolchain="msvc")
    opt = Optional(Condition(toolchain="msvc"), "/std:c++17", "/Zc:__cplusplus")
    assert list(opt(cfg)) == ["/std:c++17", "/Zc:__cplusplus"]


def test_optional_yields_nothing_when_condition_fails():
    cfg = make_config(toolchain="gcc")
    assert list(Optional(Condition(toolchain="msvc"), "/std:c++17")(cfg)) == []


def test_optional_permissive_defers_itself_when_not_yet_expandable():
    cfg = make_config(build_config=["debug", "release"])
    opt = Optional(Condition(build_config="debug"), "-g")
    assert list(opt(cfg, permissive=True)) == [opt]


def test_switch_selects_first_matching_case():
    cfg = make_config(toolchain="msvc")
    sw = Switch(
        Case(Condition(toolchain="msvc"), "/O2"),
        Case(Condition(toolchain="gcc"), "-O2"),
    )
    assert list(sw(cfg)) == ["/O2"]


def test_switch_raises_when_no_case_matches():
    cfg = make_config(toolchain="clang")
    sw = Switch(Case(Condition(toolchain="msvc"), "/O2"))
    with pytest.raises(RuntimeError, match="no cases match config"):
        list(sw(cfg))


def test_switch_permissive_defers_itself_when_not_yet_expandable():
    cfg = make_config(build_config=["debug", "release"])
    sw = Switch(Case(Condition(build_config="debug"), "-g"))
    assert list(sw(cfg, permissive=True)) == [sw]


def test_empty_condition_always_matches():
    # Condition() is the documented "match any config" used for default/fallback cases
    assert Condition()(make_config(platform="linux")) is True


def test_switch_falls_back_to_empty_condition_case():
    cfg = make_config(platform="linux")
    sw = Switch(
        Case(Condition(platform="windows"), "win"),
        Case(Condition(), "default"),  # documented fallback case
    )
    assert list(sw(cfg)) == ["default"]


def test_condition_matches_on_custom_config_field():
    # configs may carry arbitrary fields (e.g. profiler="tracy") for use in conditions
    assert Condition(profiler="tracy")(make_config(profiler="tracy")) is True
    assert Condition(profiler="tracy")(make_config(profiler="none")) is False
