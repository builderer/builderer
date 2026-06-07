from pathlib import Path

import pytest

from builderer.generators.msbuild.utils import msvc_file_rule


@pytest.mark.parametrize("name", ["a.cpp", "a.cc", "a.cxx", "a.c", "A.CPP"])
def test_msvc_file_rule_classifies_sources_as_compile(name):
    assert msvc_file_rule(Path(name)) == "ClCompile"


@pytest.mark.parametrize(
    "name", ["a.h", "a.hpp", "a.hxx", "a.inl", "a.inc", "a.tc", "a.th"]
)
def test_msvc_file_rule_classifies_headers_as_include(name):
    assert msvc_file_rule(Path(name)) == "ClInclude"


def test_msvc_file_rule_treats_extensionless_file_as_header():
    # std-style headers like Eigen's "Dense" have no extension
    assert msvc_file_rule(Path("Eigen/Dense")) == "ClInclude"


def test_msvc_file_rule_rejects_unknown_extension():
    with pytest.raises(ValueError, match="Unsupported file extension"):
        msvc_file_rule(Path("a.txt"))
