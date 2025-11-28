from typing import List, Any, Set, Union
from builderer.generators.xcode.model import (
    XcodeProject,
    Reference,
    XcodeObject,
    XcodeID,
    SourceTree,
    FileType,
    ProductType,
    YesNo,
    PBXReferenceProxy,
    PBXFileReference,
    PBXNativeTarget,
    PBXAggregateTarget,
    PBXLegacyTarget,
    ProxyType,
    BuildSetting,
)
from dataclasses import fields, is_dataclass
import os


def collect_ids(obj: Any, all_ids: Set[str]) -> None:
    if isinstance(obj, XcodeObject):
        all_ids.add(obj.id)
    elif isinstance(obj, list):
        for item in obj:
            collect_ids(item, all_ids)
    elif isinstance(obj, dict):
        for value in obj.values():
            collect_ids(value, all_ids)
    elif is_dataclass(obj):
        for field in fields(obj):
            collect_ids(getattr(obj, field.name), all_ids)


def validate_references(project: XcodeProject) -> List[str]:
    errors = []
    all_ids: set[str] = set()
    collect_ids(project, all_ids)

    def check_references(obj: Any, context: str):
        if isinstance(obj, Reference):
            if obj.id not in all_ids:
                errors.append(f"Invalid reference in {context}: {obj.id}")
        elif isinstance(obj, list):
            for index, item in enumerate(obj):
                check_references(item, f"{context}[{index}]")
        elif isinstance(obj, dict):
            for key, value in obj.items():
                check_references(value, f"{context}.{key}")
        elif is_dataclass(obj):
            for field in fields(obj):
                check_references(getattr(obj, field.name), f"{context}.{field.name}")
        elif isinstance(
            obj,
            (
                str,
                int,
                float,
                XcodeID,
                SourceTree,
                FileType,
                ProductType,
                YesNo,
                ProxyType,
                type(None),
            ),
        ):
            pass  # These are valid types and do not need further checking
        else:
            errors.append(f"Unknown type in {context}: {type(obj).__name__}")

    check_references(project, "project")

    return errors


def validate_paths(project: XcodeProject, project_dir: str) -> List[str]:
    errors = []
    # Collect product references
    product_refs: Set[XcodeID] = set()
    # From native targets (only native targets have productReference)
    for target in project.nativeTargets:
        if target.productReference is not None:
            product_refs.add(target.productReference.id)
    # From products group
    if project.project.productRefGroup is not None:
        for ref in project.groups:
            if ref.id == project.project.productRefGroup.id:
                for child in ref.children:
                    product_refs.add(child.id)

    def check_paths(obj: Any, context: str):
        if isinstance(obj, (PBXFileReference, PBXReferenceProxy)):
            # Skip product references
            if obj.id in product_refs:
                return
            # Skip references with no path
            if obj.path is None:
                return
            # Handle different source tree types
            if obj.sourceTree == SourceTree.SOURCE_ROOT:
                full_path = os.path.join(project_dir, obj.path)
                if not os.path.exists(full_path):
                    errors.append(f"File not found: {full_path}")
            elif obj.sourceTree == SourceTree.GROUP:
                # GROUP is only used for project-level singletons (main_group, products_group)
                # These don't have file paths to validate
                pass
            elif obj.sourceTree == SourceTree.BUILT_PRODUCTS_DIR:
                # Products are generated during build, can't validate existence
                pass
            else:
                errors.append(f"Unknown SourceTree {obj.sourceTree}")
        # Recurse into lists, dicts, and dataclasses
        if isinstance(obj, list):
            for index, item in enumerate(obj):
                check_paths(item, f"{context}[{index}]")
        elif isinstance(obj, dict):
            for key, value in obj.items():
                check_paths(value, f"{context}.{key}")
        elif is_dataclass(obj):
            for field in fields(obj):
                check_paths(getattr(obj, field.name), f"{context}.{field.name}")

    check_paths(project, "project")
    return errors


def _is_xcode_variable(path: Union[str, Any]) -> bool:
    if not isinstance(path, str):
        return False
    return "$(" in path and ")" in path


def validate_output_paths(project: XcodeProject) -> None:
    for target in project.nativeTargets:
        if not isinstance(target, PBXNativeTarget):
            continue
        if target.productReference is None:
            raise ValueError(f"Target {target.name} has no product reference")

        product_ref = next(
            ref
            for ref in project.fileReferences
            if ref.id == target.productReference.id
        )
        # Check for invalid filesystem characters
        if any(c in product_ref.path for c in '<>:"|?*'):
            raise ValueError(
                f"Output path '{product_ref.path}' contains invalid filesystem characters"
            )
