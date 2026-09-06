import unittest

from factories import make_cc_library, make_cc_binary, make_package, make_workspace


class TestFindTarget(unittest.TestCase):
    def test_find_target_with_package_prefix(self):
        lib = make_cc_library("liba", workspace_root="pkg")
        pkg = make_package("pkg", [lib])
        ws = make_workspace([pkg])
        _, found = ws.find_target("pkg:liba", None)
        self.assertIs(found, lib)

    def test_find_target_relative_uses_outer_package(self):
        lib = make_cc_library("liba", workspace_root="pkg")
        pkg = make_package("pkg", [lib])
        ws = make_workspace([pkg])
        _, found = ws.find_target(":liba", pkg)
        self.assertIs(found, lib)

    def test_find_target_relative_without_outer_raises(self):
        lib = make_cc_library("liba", workspace_root="pkg")
        pkg = make_package("pkg", [lib])
        ws = make_workspace([pkg])
        with self.assertRaisesRegex(RuntimeError, "unable to locate package"):
            ws.find_target(":liba", None)

    def test_find_target_malformed_name_without_colon_raises(self):
        pkg = make_package("pkg", [make_cc_library("a", workspace_root="pkg")])
        ws = make_workspace([pkg])
        with self.assertRaises(ValueError):
            ws.find_target("nocolon", None)


class TestDependencies(unittest.TestCase):
    def test_all_dependencies_raises_on_cycle(self):
        from graphlib import CycleError

        a = make_cc_library("a", workspace_root="pkg", deps=[":b"])
        b = make_cc_library("b", workspace_root="pkg", deps=[":a"])
        pkg = make_package("pkg", [a, b])
        ws = make_workspace([pkg])
        with self.assertRaises(CycleError):
            list(ws.all_dependencies(pkg, a))

    def test_direct_dependencies(self):
        a = make_cc_library("a", workspace_root="pkg")
        b = make_cc_library("b", workspace_root="pkg", deps=[":a"])
        pkg = make_package("pkg", [a, b])
        ws = make_workspace([pkg])
        self.assertEqual(list(ws.direct_dependencies(pkg, b)), [(pkg, a)])

    def test_all_dependencies_orders_dependencies_before_dependents(self):
        a = make_cc_library("a", workspace_root="pkg")
        b = make_cc_library("b", workspace_root="pkg", deps=[":a"])
        c = make_cc_library("c", workspace_root="pkg", deps=[":b"])
        main = make_cc_binary("main", workspace_root="pkg", deps=[":c"])
        pkg = make_package("pkg", [a, b, c, main])
        ws = make_workspace([pkg])
        names = [t.name for _, t in ws.all_dependencies(pkg, main)]
        # main itself is excluded; its transitive deps come in dependency-first order
        self.assertNotIn("main", names)
        self.assertLess(names.index("a"), names.index("b"))
        self.assertLess(names.index("b"), names.index("c"))

    def test_all_dependencies_dedupes_and_orders_diamond_deterministically(self):
        # main -> b, c ; b -> a ; c -> a   (a is the shared "diamond" dependency)
        def build(order):
            targets = {
                "a": make_cc_library("a", workspace_root="pkg"),
                "b": make_cc_library("b", workspace_root="pkg", deps=[":a"]),
                "c": make_cc_library("c", workspace_root="pkg", deps=[":a"]),
                "main": make_cc_binary("main", workspace_root="pkg", deps=[":b", ":c"]),
            }
            pkg = make_package("pkg")
            for name in order:
                pkg.targets[name] = targets[name]
            ws = make_workspace([pkg])
            return [t.name for _, t in ws.all_dependencies(pkg, targets["main"])]

        result = build(["a", "b", "c", "main"])
        # shared dependency appears exactly once
        self.assertEqual(result.count("a"), 1)
        # ...and before both dependents
        self.assertLess(result.index("a"), result.index("b"))
        self.assertLess(result.index("a"), result.index("c"))
        # independent of insertion order
        self.assertEqual(build(["main", "c", "b", "a"]), result)

    def test_dependencies_resolve_across_packages(self):
        lib = make_cc_library("lib", workspace_root="pkgB")
        app = make_cc_binary("app", workspace_root="pkgA", deps=["pkgB:lib"])
        pkg_a, pkg_b = make_package("pkgA", [app]), make_package("pkgB", [lib])
        ws = make_workspace([pkg_a, pkg_b])
        deps = [(p.name, t.name) for p, t in ws.all_dependencies(pkg_a, app)]
        self.assertIn(("pkgB", "lib"), deps)

    def test_dependencies_resolve_nested_package_path(self):
        lib = make_cc_library("lib", workspace_root="Parent/Child")
        app = make_cc_binary("app", workspace_root="App", deps=["Parent/Child:lib"])
        pkg_app, pkg_nested = make_package("App", [app]), make_package(
            "Parent/Child", [lib]
        )
        ws = make_workspace([pkg_app, pkg_nested])
        deps = [(p.name, t.name) for p, t in ws.all_dependencies(pkg_app, app)]
        self.assertIn(("Parent/Child", "lib"), deps)

    def test_unresolved_dependency_reference_is_an_error(self):
        app = make_cc_binary("app", workspace_root="pkg", deps=["Nope:missing"])
        with self.assertRaises(KeyError):
            make_workspace([make_package("pkg", [app])])
