import os

from io import TextIOWrapper
from pathlib import Path

from builderer import Config
from builderer.details.as_iterator import str_iter
from builderer.details.targets.target import BuildTarget
from builderer.details.workspace import Workspace
from builderer.generators.make.utils import build_config_root, mk_target_build_path, phony_target_name, is_header_only_library

class RootMakefile:
    def __init__(self, config: Config, workspace: Workspace):
        self.config = config
        self.workspace = workspace
        self.root = Path(self.config.build_root)
        self.path = self.root.joinpath("Makefile")
    
    def __call__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as file:
            self._write_makefile(file)
    
    def _write_makefile(self, file: TextIOWrapper):
        build_targets = [
            (package,target)
            for package,target in self.workspace.targets
            if isinstance(target, BuildTarget) and not is_header_only_library(target)
        ]

        # header
        file.writelines([
            f"# Generated by Builderer\n",
            "\n",
        ])

        # Validate requested configuration
        valid_arch = list(str_iter(self.config.architecture))
        valid_config = list(str_iter(self.config.build_config))
        file.writelines([
            f"ARCH ?= {valid_arch[0]}\n",
            f"CONFIG ?= {valid_config[0]}\n",
            f"VALID_ARCH := {' '.join(valid_arch)}\n",
            f"VALID_CONFIG := {' '.join(valid_config)}\n",
            f"ifeq ($(filter $(ARCH),$(VALID_ARCH)),)\n",
            f"  $(error $(ARCH) does not exist in $(VALID_ARCH))\n",
            f"endif\n",
            f"ifeq ($(filter $(CONFIG),$(VALID_CONFIG)),)\n",
            f"  $(error $(CONFIG) does not exist in $(VALID_CONFIG))\n",
            f"endif\n",
            "\n",
        ])

        # common paths
        file.writelines([
            f"BUILD_ROOT        := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))\n",
            f"BUILD_CONFIG_ROOT := {build_config_root(build_root='$(BUILD_ROOT)', arch='$(ARCH)', config='$(CONFIG)')}\n",
            f"OBJS_ROOT         := $(BUILD_CONFIG_ROOT)/.obj\n",
            f"LIBS_ROOT         := $(BUILD_CONFIG_ROOT)/.lib\n",
            f"RUNTIME_ROOT      := $(BUILD_CONFIG_ROOT)/.out\n",
            f"WORKSPACE_ROOT    := $(abspath $(BUILD_ROOT)/{Path(os.path.relpath(self.workspace.root, self.root)).as_posix()})\n",
            "\n",
        ])

        # Toolchain
        file.writelines([
          "ECHO   := echo\n",
          "MKDIR  := mkdir -p\n",
          "RM     := rm -f\n",
          "CC     := gcc\n",
          "CXX    := g++\n",
          "CCLD   := g++\n",
          "AR     := ar\n",
          "RANLIB := ranlib\n",
          "\n",
        ])

        # help
        file.writelines([
          "help:\n",
          "\t@$(ECHO) ARCH=$(ARCH)\n",
          "\t@$(ECHO) CONFIG=$(CONFIG)\n",
          "\t@$(ECHO) BUILD_ROOT=$(BUILD_ROOT)\n",
          "\t@$(ECHO) WORKSPACE_ROOT=$(WORKSPACE_ROOT)\n",
          "\n",
        ])

        # build
        file.write("build: ")
        for package,target in build_targets:
            mk_name = phony_target_name(package=package, target=target)
            file.write(f"\\\n  {mk_name} ")
        file.write("\n\n")
        
        # phony targets
        file.writelines([
            f".PHONY: help build\n"
            "\n",
            ".SUFFIXES:\n",
            "\n",
        ])

        # include target makefiles...
        for package,target in build_targets:
            mk_path = mk_target_build_path(package=package, target=target)
            file.write(f"include $(abspath $(BUILD_CONFIG_ROOT)/{mk_path.as_posix()})\n")
