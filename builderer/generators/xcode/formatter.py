"""
Xcode project file formatter.

This module provides functionality to convert an XcodeProject object into a valid
Xcode project file (.pbxproj) string representation. It uses a recursive, type-driven
approach to format the data structures without making assumptions about specific fields.
"""

import dataclasses
import enum
from typing import Dict, List, Set, Union, Optional, TypeVar, cast, Type

from builderer.generators.xcode.model import (
    XcodeObject, XcodeProject, PBXProject, Reference,
    SourceTree, FileType, ProductType, YesNo, BuildSetting,
    XcodeID
)


# Type definitions for better type safety
ObjectProperties = Dict[str, Union[str, int, bool, list, dict, XcodeObject, Reference, enum.Enum, Type]]
FormattableValue = Union[None, XcodeObject, Reference, dict, list, enum.Enum, int, float, bool, str, XcodeID, Type]
ObjectsDict = Dict[str, ObjectProperties]


def format_xcode_project(project: XcodeProject) -> str:
    """
    Convert an XcodeProject object to its string representation.
    
    Args:
        project: The XcodeProject object to format.
        
    Returns:
        A string containing the formatted Xcode project file content.
    """
    # Start with the UTF-8 marker
    result = "// !$*UTF8*$!\n"
    
    # Create the project dict structure
    project_dict: Dict[str, Union[int, dict, str, Reference]] = {
        "archiveVersion": 1,
        "classes": {},
        "objectVersion": 56,
        "objects": collect_objects(project),
        "rootObject": Reference(id=project.project.id, comment="Project object"),
    }
    
    # Format the project dictionary
    result += format_value(project_dict, 0)
    
    # Add a trailing newline
    result += "\n"
    
    return result


def collect_objects(project: XcodeProject) -> ObjectsDict:
    """
    Collect all objects from the project into a dictionary keyed by object ID.
    
    Args:
        project: The XcodeProject object to collect objects from.
        
    Returns:
        A dictionary of objects keyed by their IDs.
    """
    objects: ObjectsDict = {}
    visited: Set[int] = set()
    
    # Use introspection to iterate through all fields of the XcodeProject dataclass
    for field in dataclasses.fields(project):
        field_value = getattr(project, field.name)
        
        # Handle single object
        if isinstance(field_value, XcodeObject):
            collect_objects_recursive(field_value, objects, visited)
        
        # Handle lists of objects
        elif isinstance(field_value, list):
            for item in field_value:
                if isinstance(item, XcodeObject):
                    collect_objects_recursive(item, objects, visited)
        
        # Handle dictionaries of objects
        elif isinstance(field_value, dict):
            for item in field_value.values():
                if isinstance(item, XcodeObject):
                    collect_objects_recursive(item, objects, visited)
    
    return objects


def collect_objects_recursive(value: FormattableValue, objects: ObjectsDict, visited: Set[int]) -> None:
    """
    Recursively collect objects from a value.
    
    Args:
        value: The value to collect objects from.
        objects: The dictionary to add objects to.
        visited: Set of object ids already visited (to prevent cycles).
    """
    # Skip None values and already visited objects
    if value is None or id(value) in visited:
        return
    
    # Mark as visited to prevent cycles
    visited.add(id(value))
    
    # Process XcodeObject instances
    if isinstance(value, XcodeObject):
        # XcodeObjects always have an ID
        object_id = value.id
        object_type = value.__class__
        
        # Create the object properties
        props: ObjectProperties = {"isa": object_type}
        
        # Add all fields except id
        for field in dataclasses.fields(value):
            field_name = field.name
            field_value = getattr(value, field_name)
            
            # Skip id field and None values
            if field_name == 'id' or field_value is None:
                continue
            
            # Add to properties directly without conversion
            props[field_name] = field_value
        
        # Add to objects dictionary
        objects[object_id] = props
    
    # Process other dataclass objects recursively
    elif dataclasses.is_dataclass(value):
        for field in dataclasses.fields(value):
            field_value = getattr(value, field.name)
            # Safely handle the field value
            field_value_typed: FormattableValue = cast(FormattableValue, field_value)
            collect_objects_recursive(field_value_typed, objects, visited)
    
    # Process list values
    elif isinstance(value, list):
        for item in value:
            # Safely handle list items
            list_item_typed: FormattableValue = cast(FormattableValue, item)
            collect_objects_recursive(list_item_typed, objects, visited)
    
    # Process dictionary values
    elif isinstance(value, dict):
        for item in value.values():
            # Safely handle dict values
            dict_item_typed: FormattableValue = cast(FormattableValue, item)
            collect_objects_recursive(dict_item_typed, objects, visited)


def format_value(value: FormattableValue, indent_level: int) -> str:
    """
    Format a value based on its type.
    
    Args:
        value: The value to format.
        indent_level: The current indentation level.
        
    Returns:
        A string representing the formatted value.
    """
    indent = '\t' * indent_level
    
    # Handle None
    if value is None:
        return "(null)"
    
    # Handle XcodeID - should not be quoted
    elif isinstance(value, XcodeID):
        return value
    
    # Handle type objects - use class name without quotes
    elif isinstance(value, type):
        return value.__name__
    
    # Handle XcodeObject instances
    elif isinstance(value, XcodeObject):
        obj_id = value.id
        # If the object has a name attribute, include it as a comment
        if hasattr(value, 'name') and value.name is not None:
            return f"{obj_id} /* {value.name} */"
        return obj_id
    
    # Handle Reference objects
    elif isinstance(value, Reference):
        # References contain IDs that should not be quoted
        if value.comment:
            return f"{value.id} /* {value.comment} */"
        return value.id
    
    # Handle BuildSetting objects
    elif isinstance(value, BuildSetting):
        return format_value(value.value, indent_level)
    
    # Handle Enum values directly based on their type
    elif isinstance(value, enum.Enum):
        return format_enum(value)
    
    # Handle other dataclass objects
    elif dataclasses.is_dataclass(value):
        return format_object_dict(value.__dict__, indent_level)
    
    # Handle lists
    elif isinstance(value, list):
        return format_list(value, indent_level)
    
    # Handle dictionaries
    elif isinstance(value, dict):
        return format_dict(value, indent_level)
    
    # Handle basic types
    elif isinstance(value, (int, float, bool)):
        # Xcode represents booleans as 0/1
        if isinstance(value, bool):
            return "1" if value else "0"
        return str(value)
    
    # Handle strings - always quote them, object IDs should be handled as special XcodeID type
    elif isinstance(value, str):
        return f'"{value}"'
    
    # Raise exception for unknown types
    else:
        raise TypeError(f"Unsupported type: {type(value).__name__} for value: {value}")


def format_object_dict(obj_dict: Dict[str, FormattableValue], indent_level: int) -> str:
    """
    Format an object's dictionary representation.
    
    Args:
        obj_dict: The object's dictionary representation.
        indent_level: The current indentation level.
        
    Returns:
        A string representing the formatted object.
    """
    # Convert to regular dict for formatting
    return format_dict(obj_dict, indent_level)


def format_dict(value_dict: Dict[str, FormattableValue], indent_level: int) -> str:
    """
    Format a dictionary.
    
    Args:
        value_dict: The dictionary to format.
        indent_level: The current indentation level.
        
    Returns:
        A string representing the formatted dictionary.
    """
    indent = '\t' * indent_level
    inner_indent = '\t' * (indent_level + 1)
    
    # Empty dictionaries should have braces on separate lines for Xcode compatibility
    if not value_dict:
        return "{\n" + indent + "}"
    
    result = "{\n"
    
    # Sort keys for consistent output
    for key in sorted(value_dict.keys()):
        value = value_dict[key]
        if value is None:
            continue
        
        formatted_value = format_value(value, indent_level + 1)
        result += f"{inner_indent}{key} = {formatted_value};\n"
    
    result += f"{indent}}}"
    return result


def format_list(value_list: List[FormattableValue], indent_level: int) -> str:
    """
    Format a list.
    
    Args:
        value_list: The list to format.
        indent_level: The current indentation level.
        
    Returns:
        A string representing the formatted list.
    """
    if not value_list:
        return "()"
    
    # Handle single-item lists differently (on a single line)
    if len(value_list) == 1:
        return f"({format_value(value_list[0], indent_level)})"
    
    indent = '\t' * indent_level
    inner_indent = '\t' * (indent_level + 1)
    
    result = "(\n"
    for item in value_list:
        result += f"{inner_indent}{format_value(item, indent_level + 1)},\n"
    result += f"{indent})"
    return result


def format_enum(value_enum: enum.Enum) -> str:
    if isinstance(value_enum.value, str):
        return f'"{value_enum.value}"'
    return str(value_enum.value)
    