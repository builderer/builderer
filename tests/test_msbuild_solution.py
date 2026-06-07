"""Behavioral tests for the MSBuild .sln solution emitter (rendered to a StringIO)."""

import io

from builderer.details.workspace import target_full_name
from builderer.generators.msbuild.project import MsBuildProject
from builderer.generators.msbuild.solution import MsBuildSolution
from builderer.generators.msbuild.version import VS_VERSIONS

from conftest import (
    make_config,
    make_cc_library,
    make_cc_binary,
    make_package,
    make_workspace,
)


def _solution_text():
    lib = make_cc_library("mylib", srcs=["pkg/lib.cpp"])
    app = make_cc_binary("app", srcs=["pkg/main.cpp"], deps=[":mylib"])
    pkg = make_package("pkg", [lib, app])
    ws = make_workspace([pkg])
    config = make_config(architecture=["x64"], build_config=["debug", "release"])
    version = VS_VERSIONS[2022]
    projects = {
        target_full_name(pkg, t): MsBuildProject(config, ws, pkg, t, version)
        for t in (lib, app)
    }
    buf = io.StringIO()
    MsBuildSolution(config, ws, projects, version)._write_solution(buf)
    return buf.getvalue()


def test_solution_lists_projects_and_their_dependencies():
    out = _solution_text()
    assert '"mylib"' in out and '"app"' in out
    assert "ProjectDependencies" in out  # app depends on mylib


def test_solution_emits_config_arch_matrix():
    out = _solution_text()
    assert "debug|x64 = debug|x64" in out
    assert "release|x64 = release|x64" in out
    assert ".ActiveCfg = debug|x64" in out
    assert ".Build.0 = release|x64" in out
