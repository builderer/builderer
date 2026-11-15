"""Behavioral tests for the MSBuild .sln solution emitter (rendered to a StringIO)."""

import io
import unittest

from builderer.details.workspace import target_full_name
from builderer.generators.msbuild.project import MsBuildProject
from builderer.generators.msbuild.solution import MsBuildSolution
from builderer.generators.msbuild.version import VS_VERSIONS

from factories import (
    make_config,
    make_cc_library,
    make_cc_binary,
    make_cc_shared_library,
    make_package,
    make_workspace,
)


def _solution_text(targets):
    pkg = make_package("pkg", targets)
    ws = make_workspace([pkg])
    config = make_config(architecture=["x64"], build_config=["debug", "release"])
    version = VS_VERSIONS[2022]
    projects = {
        target_full_name(pkg, t): MsBuildProject(config, ws, pkg, t, version)
        for t in targets
    }
    buf = io.StringIO()
    MsBuildSolution(config, ws, projects, version)._write_solution(buf)
    return buf.getvalue()


def _binary_solution_text():
    lib = make_cc_library("mylib", srcs=["pkg/lib.cpp"])
    app = make_cc_binary("app", srcs=["pkg/main.cpp"], deps=[":mylib"])
    return _solution_text([lib, app])


class TestMsBuildSolution(unittest.TestCase):
    def test_solution_lists_projects_and_their_dependencies(self):
        out = _binary_solution_text()
        self.assertIn('"mylib"', out)
        self.assertIn('"app"', out)
        self.assertIn("ProjectDependencies", out)  # app depends on mylib

    def test_shared_library_lists_its_dependencies(self):
        lib = make_cc_library("mylib", srcs=["pkg/lib.cpp"])
        shared = make_cc_shared_library(
            "shared", srcs=["pkg/shared.cpp"], deps=[":mylib"]
        )
        out = _solution_text([lib, shared])
        self.assertIn('"shared"', out)
        self.assertIn("ProjectDependencies", out)  # shared depends on mylib

    def test_solution_emits_config_arch_matrix(self):
        out = _binary_solution_text()
        self.assertIn("debug|x64 = debug|x64", out)
        self.assertIn("release|x64 = release|x64", out)
        self.assertIn(".ActiveCfg = debug|x64", out)
        self.assertIn(".Build.0 = release|x64", out)
