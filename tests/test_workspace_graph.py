import pytest

from conftest import make_cc_library, make_cc_binary, make_package, make_workspace


def test_find_target_with_package_prefix():
    lib = make_cc_library("liba", workspace_root="pkg")
    pkg = make_package("pkg", [lib])
    ws = make_workspace([pkg])
    _, found = ws.find_target("pkg:liba", None)
    assert found is lib


def test_find_target_relative_uses_outer_package():
    lib = make_cc_library("liba", workspace_root="pkg")
    pkg = make_package("pkg", [lib])
    ws = make_workspace([pkg])
    _, found = ws.find_target(":liba", pkg)
    assert found is lib


def test_find_target_relative_without_outer_raises():
    lib = make_cc_library("liba", workspace_root="pkg")
    pkg = make_package("pkg", [lib])
    ws = make_workspace([pkg])
    with pytest.raises(RuntimeError, match="unable to locate package"):
        ws.find_target(":liba", None)


def test_find_target_malformed_name_without_colon_raises():
    pkg = make_package("pkg", [make_cc_library("a", workspace_root="pkg")])
    ws = make_workspace([pkg])
    with pytest.raises(ValueError):
        ws.find_target("nocolon", None)


def test_all_dependencies_raises_on_cycle():
    from graphlib import CycleError

    a = make_cc_library("a", workspace_root="pkg", deps=[":b"])
    b = make_cc_library("b", workspace_root="pkg", deps=[":a"])
    pkg = make_package("pkg", [a, b])
    ws = make_workspace([pkg])
    with pytest.raises(CycleError):
        list(ws.all_dependencies(pkg, a))


def test_direct_dependencies():
    a = make_cc_library("a", workspace_root="pkg")
    b = make_cc_library("b", workspace_root="pkg", deps=[":a"])
    pkg = make_package("pkg", [a, b])
    ws = make_workspace([pkg])
    assert list(ws.direct_dependencies(pkg, b)) == [(pkg, a)]


def test_all_dependencies_orders_dependencies_before_dependents():
    a = make_cc_library("a", workspace_root="pkg")
    b = make_cc_library("b", workspace_root="pkg", deps=[":a"])
    c = make_cc_library("c", workspace_root="pkg", deps=[":b"])
    main = make_cc_binary("main", workspace_root="pkg", deps=[":c"])
    pkg = make_package("pkg", [a, b, c, main])
    ws = make_workspace([pkg])
    names = [t.name for _, t in ws.all_dependencies(pkg, main)]
    # main itself is excluded; its transitive deps come in dependency-first order
    assert "main" not in names
    assert names.index("a") < names.index("b") < names.index("c")


def test_all_dependencies_dedupes_and_orders_diamond_deterministically():
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
    assert result.count("a") == 1  # shared dependency appears exactly once
    assert result.index("a") < result.index("b")  # ...and before both dependents
    assert result.index("a") < result.index("c")
    assert build(["main", "c", "b", "a"]) == result  # independent of insertion order


def test_dependencies_resolve_across_packages():
    lib = make_cc_library("lib", workspace_root="pkgB")
    app = make_cc_binary("app", workspace_root="pkgA", deps=["pkgB:lib"])
    pkg_a, pkg_b = make_package("pkgA", [app]), make_package("pkgB", [lib])
    ws = make_workspace([pkg_a, pkg_b])
    deps = [(p.name, t.name) for p, t in ws.all_dependencies(pkg_a, app)]
    assert ("pkgB", "lib") in deps


def test_dependencies_resolve_nested_package_path():
    lib = make_cc_library("lib", workspace_root="Parent/Child")
    app = make_cc_binary("app", workspace_root="App", deps=["Parent/Child:lib"])
    pkg_app, pkg_nested = make_package("App", [app]), make_package(
        "Parent/Child", [lib]
    )
    ws = make_workspace([pkg_app, pkg_nested])
    deps = [(p.name, t.name) for p, t in ws.all_dependencies(pkg_app, app)]
    assert ("Parent/Child", "lib") in deps


def test_unresolved_dependency_reference_is_an_error():
    app = make_cc_binary("app", workspace_root="pkg", deps=["Nope:missing"])
    with pytest.raises(KeyError):
        make_workspace([make_package("pkg", [app])])
