"""Flat names: the "/"-free, ":"-free stand-ins for canonical "pkg/path:target"
names used by Xcode schemes and make. The spec under test:

- "/" maps to "." and ":" maps to "@".
- "@" is reserved in package and target names; ":" in both; "/" in targets.
- "." stays legal (versioned directories, "foo.app" targets), so packages that
  only differ by "/" vs "." are rejected instead.
- Together these make flat names collision-free across a workspace.
"""

import itertools
import unittest
from pathlib import Path

from builderer.details.context import BuildContext
from builderer.details.naming import (
    check_package_name_conflicts,
    flat_package_name,
    flat_target_name,
    validate_package_name,
    validate_target_name,
)
from builderer.details.package import Package
from builderer.details.targets.cc_library import CCLibrary


class TestFlatTargetName(unittest.TestCase):
    def test_canonical_names_map_slash_to_dot_and_colon_to_at(self):
        for package, target, flat in [
            ("pkg", "t", "pkg@t"),
            ("MyProject/SubModule", "app", "MyProject.SubModule@app"),
            ("a/b/c", "t", "a.b.c@t"),
            ("External/zlib-1.3.1", "zlib", "External.zlib-1.3.1@zlib"),
            ("apps", "calc.app", "apps@calc.app"),
            ("External/libc++", "c++", "External.libc++@c++"),
        ]:
            with self.subTest(package=package, target=target):
                self.assertEqual(flat_target_name(package, target), flat)

    def test_workspace_root_package_has_an_empty_package_part(self):
        # a BUILD file at the workspace root is package "." -- its flat name must
        # not start with "." (a hidden file for Xcode schemes)
        self.assertEqual(flat_package_name("."), "")
        self.assertEqual(flat_target_name(".", "tool"), "@tool")

    def test_flat_names_never_contain_slash_or_colon(self):
        flat = flat_target_name("a/b/c/d", "e.app")
        self.assertNotIn("/", flat)
        self.assertNotIn(":", flat)

    def test_valid_non_conflicting_names_never_share_a_flat_name(self):
        # exhaustive over names built from the characters that do stay legal and
        # are most likely to confuse the mapping ("." in both packages and targets)
        parts = ["a", "b", "a.b", "b.a", "a.b.c"]
        packages = ["."] + [
            "/".join(p) for n in (1, 2) for p in itertools.product(parts, repeat=n)
        ]
        targets = parts
        valid_packages = [
            p
            for p in packages
            if not any(
                flat_package_name(p) == flat_package_name(q) and p != q
                for q in packages
            )
        ]
        names = [(p, t) for p in valid_packages for t in targets]
        flats = [flat_target_name(p, t) for p, t in names]
        self.assertEqual(len(flats), len(set(flats)))


class TestReservedCharacters(unittest.TestCase):
    def test_package_names_reject_at_and_colon_in_any_directory(self):
        for name in ["a@b", "a:b", "x/a@b", "x/a:b/y", "@", "pkg@1.2/src"]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError) as ctx:
                    validate_package_name(name)
                self.assertIn(name, str(ctx.exception))

    def test_package_names_allow_dots_and_cxx_style_directories(self):
        for name in [".", "pkg", "External/zlib-1.3.1", "python3.9", "libc++", "a.b/c"]:
            with self.subTest(name=name):
                validate_package_name(name)  # must not raise

    def test_target_names_reject_at_slash_and_colon(self):
        for name in ["a@b", "a/b", "a:b", "@", "lib@2x"]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError) as ctx:
                    validate_target_name(name)
                self.assertIn(name, str(ctx.exception))

    def test_target_names_allow_app_bundles_and_cxx_names(self):
        for name in ["calc.app", "c++", "libc++abi", "zlib-1.3.1", "a_b"]:
            with self.subTest(name=name):
                validate_target_name(name)  # must not raise

    def test_add_package_rejects_reserved_characters(self):
        ctx = BuildContext(Path("a@b"))
        with self.assertRaises(ValueError):
            ctx.add_package("a@b")
        self.assertEqual(ctx.packages, {})

    def test_add_target_rejects_reserved_characters(self):
        pkg = Package(name="pkg", root=Path("pkg"))
        for name in ["x@y", "x/y", "x:y"]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    pkg.add_target(target_type=CCLibrary, name=name)
        self.assertEqual(pkg.targets, {})

    def test_add_target_accepts_dotted_names(self):
        pkg = Package(name="pkg", root=Path("pkg"))
        pkg.add_target(target_type=CCLibrary, name="c++")
        pkg.add_target(target_type=CCLibrary, name="zlib-1.3.1")
        self.assertEqual(set(pkg.targets), {"c++", "zlib-1.3.1"})


class TestPackageNameConflicts(unittest.TestCase):
    def test_slash_and_dot_twins_conflict_and_both_are_named(self):
        with self.assertRaises(ValueError) as ctx:
            check_package_name_conflicts(["python/3.9", "python.3.9"])
        self.assertIn("python/3.9", str(ctx.exception))
        self.assertIn("python.3.9", str(ctx.exception))

    def test_dots_moved_between_directories_conflict(self):
        # "a.b/c" and "a/b.c" both read as "a.b.c"
        with self.assertRaises(ValueError):
            check_package_name_conflicts(["a.b/c", "a/b.c"])

    def test_similar_but_distinct_names_do_not_conflict(self):
        check_package_name_conflicts(
            [".", "python/3.9", "python3.9", "python/39", "a/b", "a/b/c", "ab"]
        )

    def test_error_message_does_not_depend_on_input_order(self):
        messages = set()
        for names in (["x/y", "x.y"], ["x.y", "x/y"]):
            with self.assertRaises(ValueError) as ctx:
                check_package_name_conflicts(names)
            messages.add(str(ctx.exception))
        self.assertEqual(len(messages), 1)

    def test_accepts_a_dict_of_packages(self):
        # Workspace passes its {name: Package} dict straight through
        with self.assertRaises(ValueError):
            check_package_name_conflicts({"p/q": object(), "p.q": object()})


if __name__ == "__main__":
    unittest.main()
