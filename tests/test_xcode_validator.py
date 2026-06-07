"""The validator's job is to CATCH malformed projects, so these tests feed it broken
models and assert it complains. (The happy path -- a real generated model passing
validation -- is covered by test_xcode_generator.)
"""

import pytest

from builderer.generators.xcode.validator import (
    validate_references,
    validate_output_paths,
)
from builderer.generators.xcode.model import (
    XcodeID,
    XcodeProject,
    Reference,
    SourceTree,
    PBXFileReference,
    PBXGroup,
    PBXProject,
    PBXNativeTarget,
    XCBuildConfiguration,
    XCConfigurationList,
    ProductType,
)


def _minimal_project(*, targets=None, file_refs=None, native_targets=None):
    bc = XCBuildConfiguration(name="Debug", buildSettings={})
    cfg_list = XCConfigurationList(buildConfigurations=[Reference(bc.id)])
    main_group = PBXGroup(name="Main", sourceTree=SourceTree.GROUP, children=[])
    products_group = PBXGroup(name="Products", sourceTree=SourceTree.GROUP, children=[])
    project = PBXProject(
        name="P",
        buildConfigurationList=Reference(cfg_list.id),
        mainGroup=Reference(main_group.id),
        productRefGroup=Reference(products_group.id),
        targets=targets if targets is not None else [],
    )
    return XcodeProject(
        fileReferences=file_refs or [],
        groups=[main_group, products_group],
        buildFiles=[],
        buildPhases=[],
        nativeTargets=native_targets or [],
        project=project,
        buildConfigurations=[bc],
        configurationLists=[cfg_list],
    )


def _native_target(file_ref):
    return PBXNativeTarget(
        name="T",
        buildConfigurationList=Reference(XcodeID("0" * 24)),
        buildPhases=[],
        dependencies=[],
        productName="T",
        productReference=Reference(file_ref.id),
        productType=ProductType.APPLICATION,
    )


def test_validate_references_flags_a_dangling_reference():
    project = _minimal_project(targets=[Reference(XcodeID("DEADBEEF" * 3))])
    assert any("DEADBEEF" in e for e in validate_references(project))


def test_validate_output_paths_rejects_invalid_filesystem_chars():
    file_ref = PBXFileReference(
        name="bad", path="out:put.app", sourceTree=SourceTree.BUILT_PRODUCTS_DIR
    )
    project = _minimal_project(
        file_refs=[file_ref], native_targets=[_native_target(file_ref)]
    )
    with pytest.raises(ValueError, match="invalid filesystem characters"):
        validate_output_paths(project)
