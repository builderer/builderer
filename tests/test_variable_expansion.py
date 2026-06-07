import pytest

from builderer import Condition, Optional, Switch, Case
from builderer.details.variable_expansion import (
    resolve_conditionals,
    resolve_variables,
    bake_config,
)

from conftest import make_config


@pytest.mark.parametrize(
    "platform,expected",
    [
        ("windows", "win.cpp"),
        ("linux", "linux.cpp"),
        ("macos", "mac.mm"),
    ],
)
def test_resolve_conditionals_selects_sources_for_the_active_platform(
    platform, expected
):
    # one Optional per platform: exactly the active platform's source survives,
    # exercising both the "matched -> expand" and "unmatched -> drop" paths at once
    srcs = [
        "common.cpp",
        Optional(Condition(platform="windows"), "win.cpp"),
        Optional(Condition(platform="linux"), "linux.cpp"),
        Optional(Condition(platform="macos"), "mac.mm"),
    ]
    assert resolve_conditionals(make_config(platform=platform), srcs) == [
        "common.cpp",
        expected,
    ]


def test_resolve_conditionals_recurses_into_nested_lists():
    cfg = make_config(toolchain="msvc")
    value = [["a", Optional(Condition(toolchain="msvc"), "b")]]
    assert resolve_conditionals(cfg, value) == [["a", "b"]]


def test_resolve_conditionals_bare_switch_resolves_to_single_value():
    cfg = make_config(toolchain="msvc")
    sw = Switch(Case(Condition(toolchain="msvc"), "/O2"))
    assert resolve_conditionals(cfg, sw) == "/O2"


def test_resolve_variables_substitutes_into_strings_and_lists():
    cfg = make_config()
    assert resolve_variables(cfg, {"name": "foo"}, "lib{name}.a") == "libfoo.a"
    assert resolve_variables(cfg, {"x": "1"}, ["a{x}", "b{x}"]) == ["a1", "b1"]


def test_bake_config_collapses_lists_to_the_chosen_scalars():
    cfg = make_config(architecture=["x64", "arm64"], build_config=["debug", "release"])
    baked = bake_config(cfg, architecture="arm64", build_config="release")
    assert (baked.architecture, baked.build_config) == ("arm64", "release")


def test_bake_config_does_not_mutate_the_original():
    cfg = make_config(architecture=["x64"], build_config=["debug"])
    bake_config(cfg, architecture="x64", build_config="debug")
    assert cfg.architecture == ["x64"] and cfg.build_config == ["debug"]


def test_bake_config_rejects_values_not_present_in_the_config():
    cfg = make_config(architecture=["x64"], build_config=["debug"])
    with pytest.raises(AssertionError):
        bake_config(cfg, architecture="ppc", build_config="debug")
    with pytest.raises(AssertionError):
        bake_config(cfg, architecture="x64", build_config="profile")
