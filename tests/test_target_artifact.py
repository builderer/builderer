import unittest
from pathlib import Path

from builderer.details.context import ConfigContext
from builderer.details.target_artifact import (
    artifact_root,
    check_artifact_collisions,
    _default_artifact_filename,
    _default_artifact_subpath,
    get_target_artifact_subpath,
    _resolve_config_variant,
)
from builderer.details.targets.target import BuildTarget

from factories import (
    make_config,
    make_cc_library,
    make_cc_binary,
    make_apple_application,
    make_package,
    make_workspace,
)


class TestArtifactFilename(unittest.TestCase):
    def test_artifact_filenames_across_all_platforms(self):
        for platform, lib_name, bin_name in [
            ("windows", "a.lib", "app.exe"),
            ("linux", "liba.a", "app"),
            ("macos", "liba.a", "app"),
            ("emscripten", "liba.a", "app"),
        ]:
            with self.subTest(platform=platform):
                cfg = make_config(
                    platform=platform, architecture="x64", build_config="debug"
                )
                self.assertEqual(
                    _default_artifact_filename(cfg, make_cc_library("a")), lib_name
                )
                self.assertEqual(
                    _default_artifact_filename(cfg, make_cc_binary("app")), bin_name
                )

    def test_apple_application_filename_gets_app_suffix(self):
        cfg = make_config(platform="macos", architecture="arm64", build_config="debug")
        app = make_apple_application(
            "MyApp", binary=":app", info_plist={"CFBundleName": "MyApp"}
        )
        self.assertEqual(_default_artifact_filename(cfg, app), "MyApp.app")

    def test_unsupported_target_type_raises_typeerror(self):
        class _Other(BuildTarget):
            pass

        with self.assertRaises(TypeError):
            _default_artifact_filename(
                make_config(), _Other(name="x", workspace_root="pkg")
            )


class TestArtifactSubpath(unittest.TestCase):
    def test_default_subpath_layout(self):
        cfg = make_config(
            platform="windows",
            architecture="x64",
            build_config="debug",
            buildtool="vs2022",
            build_root="Out/build/windows",
        )
        self.assertEqual(
            _default_artifact_subpath(cfg, "pkg", make_cc_library("a")),
            Path("Out/build/windows/.artifacts/x64/debug/pkg/a.lib"),
        )

    def test_xcode_artifacts_go_beside_the_project_bundle_not_inside_it(self):
        # Xcode owns the .xcodeproj bundle, so outputs go beside it in <name>.noindex
        cfg = make_config(
            platform="macos",
            architecture="arm64",
            build_config="debug",
            buildtool="xcode",
            build_root="Out/build/macos-xcode.xcodeproj",
        )
        self.assertEqual(
            _default_artifact_subpath(cfg, "pkg", make_cc_library("a")),
            Path("Out/build/macos-xcode.noindex/.artifacts/arm64/debug/pkg/liba.a"),
        )

    def test_packages_map_to_directories(self):
        cfg = make_config(platform="linux", architecture="x86-64", build_config="debug")
        self.assertEqual(
            _default_artifact_subpath(cfg, "a/b", make_cc_library("t")),
            Path("Out/build/windows/.artifacts/x86-64/debug/a/b/libt.a"),
        )
        # the workspace-root package adds no directory
        self.assertEqual(
            _default_artifact_subpath(cfg, ".", make_cc_binary("tool")),
            Path("Out/build/windows/.artifacts/x86-64/debug/tool"),
        )

    def test_artifact_root_keeps_directory_build_roots_even_when_dotted(self):
        for build_root in ["Out/build/linux", "Out/build/v1.2", "Out/build/x.sln"]:
            with self.subTest(build_root=build_root):
                cfg = make_config(build_root=build_root)
                self.assertEqual(artifact_root(cfg), Path(build_root))

    def test_output_path_override_replaces_the_default(self):
        cfg = make_config(platform="windows", architecture="x64", build_config="debug")
        lib = make_cc_library("a", output_path="custom/dir/special.lib")
        self.assertEqual(
            get_target_artifact_subpath(cfg, "pkg", lib), Path("custom/dir/special.lib")
        )


def _linux(**over):
    over.setdefault("architecture", ["x86-64"])
    over.setdefault("build_config", ["debug"])
    return make_config(platform="linux", toolchain="gcc", buildtool="make", **over)


class TestArtifactCollisions(unittest.TestCase):
    def test_ordinary_workspace_passes(self):
        a = make_package(
            "a",
            [
                make_cc_library("lib", workspace_root="a", srcs=["a/l.c"]),
                make_cc_binary("app", workspace_root="a", srcs=["a/m.c"]),
            ],
        )
        # same target names in another package are fine
        b = make_package(
            "a/sub",
            [make_cc_library("lib", workspace_root="a/sub", srcs=["a/sub/l.c"])],
        )
        check_artifact_collisions(make_workspace([a, b]), _linux())

    def test_library_and_binary_with_the_same_filename_collide(self):
        pkg = make_package(
            "pkg",
            [
                make_cc_library("foo", srcs=["pkg/l.c"]),
                make_cc_binary("libfoo.a", srcs=["pkg/m.c"]),
            ],
        )
        with self.assertRaises(ValueError) as ctx:
            check_artifact_collisions(make_workspace([pkg]), _linux())
        self.assertIn("pkg:foo", str(ctx.exception))
        self.assertIn("pkg:libfoo.a", str(ctx.exception))

    def test_header_only_library_produces_nothing_to_collide_with(self):
        pkg = make_package(
            "pkg",
            [
                make_cc_library("foo", hdrs=["pkg/foo.h"]),
                make_cc_binary("libfoo.a", srcs=["pkg/m.c"]),
            ],
        )
        check_artifact_collisions(make_workspace([pkg]), _linux())

    def test_identical_output_paths_collide(self):
        pkg = make_package(
            "pkg",
            [
                make_cc_binary("a", srcs=["pkg/a.c"], output_path="Out/bin/tool"),
                make_cc_binary("b", srcs=["pkg/b.c"], output_path="Out/bin/./tool"),
            ],
        )
        with self.assertRaises(ValueError) as ctx:
            check_artifact_collisions(make_workspace([pkg]), _linux())
        self.assertIn("x86-64/debug", str(ctx.exception))

    def test_output_paths_differing_only_by_case_collide(self):
        # one file on macOS and Windows filesystems
        pkg = make_package(
            "pkg",
            [
                make_cc_binary("a", srcs=["pkg/a.c"], output_path="Out/bin/Tool"),
                make_cc_binary("b", srcs=["pkg/b.c"], output_path="Out/bin/tool"),
            ],
        )
        with self.assertRaises(ValueError):
            check_artifact_collisions(make_workspace([pkg]), _linux())

    def test_output_path_shared_across_architectures_is_allowed(self):
        app = make_cc_binary("app", srcs=["pkg/a.c"], output_path="Out/linux/app")
        check_artifact_collisions(
            make_workspace([make_package("pkg", [app])]),
            _linux(architecture=["x86-64", "i686"], build_config=["debug", "release"]),
        )

    def test_default_artifact_on_a_package_directory_collides(self):
        lib = make_cc_library("x", workspace_root="a", srcs=["a/x.c"])
        sub = make_cc_library("y", workspace_root="a/libx.a", srcs=["a/libx.a/y.c"])
        ws = make_workspace([make_package("a", [lib]), make_package("a/libx.a", [sub])])
        with self.assertRaises(ValueError) as ctx:
            check_artifact_collisions(ws, _linux())
        self.assertIn("a:x", str(ctx.exception))
        self.assertIn("a/libx.a", str(ctx.exception))


class TestUniqueBuildRoots(unittest.TestCase):
    def _add(self, ctx, name, build_root):
        ctx.add_config(
            name,
            buildtool="make",
            toolchain="gcc",
            platform="linux",
            sandbox_root="Out/.sandbox",
            build_root=build_root,
            build_config=["debug"],
            architecture=["x86-64"],
        )

    def test_configs_sharing_a_build_root_are_rejected(self):
        ctx = ConfigContext(Path("."))
        self._add(ctx, "gcc", "Out/build/linux")
        with self.assertRaises(ValueError) as err:
            self._add(ctx, "clang", "Out/build/./linux/")
        self.assertIn("gcc", str(err.exception))
        self.assertIn("clang", str(err.exception))

    def test_distinct_build_roots_are_allowed(self):
        ctx = ConfigContext(Path("."))
        self._add(ctx, "linux", "Out/build/linux")
        self._add(ctx, "linux-clang", "Out/build/linux-clang")
        self.assertEqual(set(ctx.configs), {"linux", "linux-clang"})


class TestResolveConfigVariant(unittest.TestCase):
    def test_resolve_config_variant_defaults_to_first_then_honors_explicit(self):
        cfg = make_config(
            architecture=["x64", "arm64"], build_config=["debug", "release"]
        )
        first = _resolve_config_variant(cfg, None, None)
        self.assertEqual((first.architecture, first.build_config), ("x64", "debug"))
        explicit = _resolve_config_variant(cfg, "release", "arm64")
        self.assertEqual(
            (explicit.architecture, explicit.build_config), ("arm64", "release")
        )
