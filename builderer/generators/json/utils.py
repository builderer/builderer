import os
from pathlib import Path


def is_header_file(filename):
    header_extensions = [".h", ".hpp", ".hxx", ".hh", ".h++", ".inc"]
    _, ext = os.path.splitext(filename)
    return ext.lower() in header_extensions


def is_source_file(filename):
    source_extensions = [".c", ".cpp", ".cxx", ".cc", ".c++", ".m", ".mm"]
    _, ext = os.path.splitext(filename)
    return ext.lower() in source_extensions


def categorize_files(files):
    return {
        "header_files": [f for f in files if is_header_file(f)],
        "source_files": [f for f in files if is_source_file(f)],
    }
