from pathlib import Path
from typing import Dict, Type

from builderer.details.targets.apple_application import AppleApplication
from builderer.details.targets.cc_binary import CCBinary
from builderer.details.targets.cc_library import CCLibrary
from builderer.details.targets.file_group import FileGroup
from builderer.details.targets.generate_files import GenerateFiles
from builderer.details.targets.git_repository import GitRepository
from builderer.details.targets.https_repository import HttpsRepository
from builderer.details.targets.metal_library import MetalLibrary
from builderer.details.targets.swift_binary import SwiftBinary
from builderer.details.targets.swift_cc_module import SwiftCcModule
from builderer.details.targets.swift_library import SwiftLibrary
from builderer.details.targets.target import Target


class BuiltinRules:
    def __init__(self, outer):
        self.outer = outer

    def git_repository(self, **kwargs):
        self.outer.add_target(target_type=GitRepository, **kwargs)

    def https_repository(self, **kwargs):
        self.outer.add_target(target_type=HttpsRepository, **kwargs)

    def generate_files(self, **kwargs):
        self.outer.add_target(target_type=GenerateFiles, **kwargs)

    def file_group(self, **kwargs):
        self.outer.add_target(target_type=FileGroup, **kwargs)

    def cc_library(self, **kwargs):
        self.outer.add_target(target_type=CCLibrary, **kwargs)

    def cc_binary(self, **kwargs):
        self.outer.add_target(target_type=CCBinary, **kwargs)

    def apple_application(self, **kwargs):
        self.outer.add_target(target_type=AppleApplication, **kwargs)

    def swift_library(self, **kwargs):
        self.outer.add_target(target_type=SwiftLibrary, **kwargs)

    def swift_binary(self, **kwargs):
        self.outer.add_target(target_type=SwiftBinary, **kwargs)

    def swift_cc_module(self, **kwargs):
        self.outer.add_target(target_type=SwiftCcModule, **kwargs)

    def metal_library(self, **kwargs):
        self.outer.add_target(target_type=MetalLibrary, **kwargs)


class Package:
    def __init__(self, name: str, root: Path):
        self.name = name
        self.root = root
        self.targets: Dict[str, Target] = {}
        self.builtin = BuiltinRules(self)

    def add_target(self, target_type: Type[Target], **kwargs):
        target = target_type(**kwargs, workspace_root=self.root.as_posix())
        if target.name in self.targets:
            raise ValueError(
                f"target with name='{target.name}' already exists in package='{self.name}'"
            )
        self.targets[target.name] = target
