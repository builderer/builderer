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
)
from dataclasses import fields, is_dataclass
import os


def collect_ids(obj: Any, all_ids: Set[str]) -> None:
    """
    Recursively collect all IDs from the project structure.

    Args:
        obj: The object to traverse.
        all_ids: A set to collect IDs.
    """
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
    """
    Validate that all references in the Xcode project point to existing objects.

    Args:
        project: The Xcode project to validate.

    Returns:
        A list of error messages for invalid references.
    """
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
    """
    Validate that all file paths in the project exist.

    Args:
        project: The Xcode project to validate.
        project_dir: The project directory (where the .xcodeproj lives).

    Returns:
        A list of error messages for missing files.
    """
    errors = []

    # Collect product references
    product_refs: Set[XcodeID] = set()

    # From all target types
    for target in (
        project.nativeTargets + project.aggregateTargets + project.legacyTargets
    ):
        if hasattr(target, "productReference") and target.productReference is not None:
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
                # GROUP paths are relative to their parent group, which we can't easily validate
                # without tracking group hierarchy. Skip for now.
                pass
            elif obj.sourceTree == SourceTree.DEVELOPER_DIR:
                # These are Xcode-provided files, assume they exist
                pass
            elif obj.sourceTree == SourceTree.SDKROOT:
                # These are SDK-provided files, assume they exist
                pass
            elif obj.sourceTree == SourceTree.ABSOLUTE:
                if not os.path.exists(obj.path):
                    errors.append(f"File not found: {obj.path}")
            else:
                errors.append(f"Unknown sourceTree value: {obj.sourceTree}")

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
