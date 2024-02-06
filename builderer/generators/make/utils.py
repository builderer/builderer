from pathlib import Path

from builderer.details.targets.cc_library import CCLibrary
from builderer.details.variable_expansion import resolve_conditionals

def build_config_root(build_root: str, arch: str, config: str) -> str:
    return f"{build_root}/{arch}/{config}"

def mk_target_build_path(package, target):
    return Path(package.name).joinpath(f"{target.name}.mk")

def phony_target_name(package, target):
    return f"{package.name}@{target.name}"

def is_header_only_library(target):
    if isinstance(target, CCLibrary):
        return not bool(target.srcs)
    else:
        return False

def cc_library_output_path(config, package, target):
    assert not is_header_only_library(target)
    output_path = resolve_conditionals(config=config, value=target.output_path)
    if output_path:
        return f"$(WORKSPACE_ROOT)/{output_path}"
    return f"$(LIBS_ROOT)/{package.name}/lib{target.name}.a"

def cc_binary_output_path(config, package, target):
    output_path = resolve_conditionals(config=config, value=target.output_path)
    if output_path:
        return f"$(WORKSPACE_ROOT)/{output_path}"
    return f"$(RUNTIME_ROOT)/{package.name}/{target.name}"