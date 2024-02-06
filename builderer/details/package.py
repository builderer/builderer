from pathlib import Path
from typing import Dict, Type

from builderer.details.targets.cc_binary import CCBinary
from builderer.details.targets.cc_library import CCLibrary
from builderer.details.targets.generate_files import GenerateFiles
from builderer.details.targets.git_repository import GitRepository
from builderer.details.targets.target import Target

class BuiltinRules:
    def __init__(self, outer):
        self.outer = outer
    
    def git_repository(self, **kwargs):
        self.outer.add_target(target_type=GitRepository, **kwargs)

    def generate_files(self, **kwargs):
        self.outer.add_target(target_type=GenerateFiles, **kwargs)

    def cc_library(self, **kwargs):
        self.outer.add_target(target_type=CCLibrary, **kwargs)
    
    def cc_binary(self, **kwargs):
        self.outer.add_target(target_type=CCBinary, **kwargs)

class Package:
    def __init__(self, name: str, root: Path):
        self.name = name
        self.root = root
        self.targets: Dict[str,Target] = {}
        self.builtin = BuiltinRules(self)
    
    def add_target(self, target_type: Type[Target], **kwargs):
        target = target_type(**kwargs, workspace_root=self.root.as_posix())
        if target.name in self.targets:
            raise ValueError(f"target with name='{target.name}' already exists in package='{self.name}'")
        self.targets[target.name] = target

