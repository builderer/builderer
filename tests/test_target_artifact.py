from pathlib import Path

import pytest

from builderer.details.target_artifact import (
    _default_artifact_filename,
    _default_artifact_subpath,
    get_target_artifact_subpath,
    _resolve_config_variant,
)
from builderer.details.targets.target import BuildTarget

from conftest import (
    make_config,
    make_cc_library,
    make_cc_binary,
    make_apple_application,
)


@pytest.mark.parametrize(
    "platform,lib_name,bin_name",
    [
        ("windows", "a.lib", "app.exe"),
        ("linux", "liba.a", "app"),
        ("macos", "liba.a", "app"),
        ("emscripten", "liba.a", "app"),
    ],
)
def test_artifact_filenames_across_all_platforms(platform, lib_name, bin_name):
    cfg = make_config(platform=platform, architecture="x64", build_config="debug")
    assert _default_artifact_filename(cfg, make_cc_library("a")) == lib_name
    assert _default_artifact_filename(cfg, make_cc_binary("app")) == bin_name


def test_apple_application_filename_gets_app_suffix():
    cfg = make_config(platform="macos", architecture="arm64", build_config="debug")
    app = make_apple_application(
        "MyApp", binary=":app", info_plist={"CFBundleName": "MyApp"}
    )
    assert _default_artifact_filename(cfg, app) == "MyApp.app"


def test_default_subpath_layout():
    cfg = make_config(
        platform="windows",
        architecture="x64",
        build_config="debug",
        buildtool="vs2022",
        build_root="Out/build/windows",
    )
    assert _default_artifact_subpath(cfg, "pkg", make_cc_library("a")) == Path(
        "Out/build/windows/.artifacts/x64/debug/vs2022/libs/pkg/a.lib"
    )


def test_output_path_override_replaces_the_default():
    cfg = make_config(platform="windows", architecture="x64", build_config="debug")
    lib = make_cc_library("a", output_path="custom/dir/special.lib")
    assert get_target_artifact_subpath(cfg, "pkg", lib) == Path(
        "custom/dir/special.lib"
    )


def test_unsupported_target_type_raises_typeerror():
    class _Other(BuildTarget):
        pass

    with pytest.raises(TypeError):
        _default_artifact_filename(
            make_config(), _Other(name="x", workspace_root="pkg")
        )


def test_resolve_config_variant_defaults_to_first_then_honors_explicit():
    cfg = make_config(architecture=["x64", "arm64"], build_config=["debug", "release"])
    first = _resolve_config_variant(cfg, None, None)
    assert (first.architecture, first.build_config) == ("x64", "debug")
    explicit = _resolve_config_variant(cfg, "release", "arm64")
    assert (explicit.architecture, explicit.build_config) == ("arm64", "release")
