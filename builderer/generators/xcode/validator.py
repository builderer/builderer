from typing import List, Any, Set
from builderer.generators.xcode.model import (
    XcodeProject,
    Reference,
    XcodeObject,
    XcodeID,
    SourceTree,
    FileType,
    ProductType,
    YesNo,
)
from dataclasses import fields, is_dataclass


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
                type(None),
            ),
        ):
            pass  # These are valid types and do not need further checking
        else:
            errors.append(f"Unknown type in {context}: {type(obj).__name__}")

    check_references(project, "project")

    return errors
