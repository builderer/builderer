import io
import os

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Dict, List, Optional, TextIO

from builderer.details.file_types import C_FAMILY_KINDS, FileKind, file_kind
from builderer.details.file_utils import write_text_if_changed
from builderer.details.naming import flat_target_name
from builderer.details.plist_xml import plist_dict_to_xml_text
from builderer.details.targets.apple_application import (
    AppleApplication,
    validate_resolved_info_plist,
)
from builderer.details.targets.cc_binary import CCBinary
from builderer.details.targets.cc_library import CCLibrary
from builderer.details.targets.metal_library import MetalLibrary
from builderer.details.targets.swift_binary import SwiftBinary
from builderer.details.targets.swift_cc_module import SwiftCcModule
from builderer.details.targets.swift_library import SwiftLibrary
from builderer.details.variable_expansion import resolve_conditionals
from builderer.generators.make.utils import (
    apple_application_output_path,
    apple_bundle_resource_dir,
    cc_binary_output_path_workspace,
    metal_library_output_path,
    mk_target_build_path,
    object_subpaths,
    options_build_path,
    target_obj_dir,
    phony_target_name,
    is_header_only_library,
    cc_library_output_path,
    cc_binary_output_path,
    swift_library_output_path,
    swift_binary_output_path,
    swift_module_path,
    swift_module_dir,
    swift_header_dir,
)

# The compile command for each kind of C-family source. Every C-family kind must
# be listed: there is no fallback, so a kind without a command fails generation.
COMPILE_COMMANDS: Dict[FileKind, str] = {
    FileKind.C: "CC_COMPILE",
    FileKind.OBJC: "CC_COMPILE",
    FileKind.ASM: "CC_COMPILE",
    FileKind.CXX: "CXX_COMPILE",
    FileKind.OBJCXX: "CXX_COMPILE",
}


# TODO: likely should be [toolchain][arch] instead...
SWIFT_PLATFORM_ARCH_FLAGS = {
    # swiftc uses -target <triple> instead of -arch. We emit the bare triple
    # (arch + os, no version). Users supply the deployment-version-bearing
    # -target via swift_flags in their RULES.builderer; later flags win, so
    # the user's choice overrides this default.
    #
    # Triples below are the canonical Swift toolchain identifiers documented
    # by swiftlang (e.g. Linux swiftmodule paths use x86_64-unknown-linux-gnu;
    # the Windows port targets x86_64-unknown-windows-msvc). Uncommon archs
    # not listed here fall through to an empty string -- users supply a full
    # -target via swift_flags.
    "macos": {
        "x86_64": "-target x86_64-apple-macos",
        "arm64": "-target arm64-apple-macos",
    },
    "linux": {
        "x86-64": "-target x86_64-unknown-linux-gnu",
        # 64-bit ARM Linux uses the aarch64 triple regardless of the armvN-a name
        "armv8-a": "-target aarch64-unknown-linux-gnu",
        "armv9-a": "-target aarch64-unknown-linux-gnu",
    },
    "windows": {
        "x64": "-target x86_64-unknown-windows-msvc",
    },
}


# (sdk, AIR target triple) per Apple platform. Metal is NOT keyed by CPU
# architecture: .metal compiles to AIR (Apple's GPU intermediate
# representation), whose target is air64-apple-<os> regardless of whether the
# app's CPU arch is x86_64 or arm64; the resulting .metallib is GPU bytecode
# specialized to the GPU at runtime, not to the CPU. The only axis that varies
# is platform/SDK. The user may supply a fully versioned -target via metal_flags
# (later flags win), mirroring how the swift writer lets the user override the
# bare triple.
METAL_PLATFORM = {
    "macos": ("macosx", "air64-apple-macos"),
    "ios": ("iphoneos", "air64-apple-ios"),
    # extend with tvos/watchos/visionos alongside the rest of the generator
}

PLATFORM_ARCH_FLAGS = {
    "linux": {
        "x86-64": "-m64 -march=x86-64",
        "i386": "-m32 -march=i386",
        "i686": "-m32 -march=i686",
        # Arm list from: https://gcc.gnu.org/onlinedocs/gcc/AArch64-Options.html
        "armv8-a": "-march=armv8-a",
        "armv8.1-a": "-march=armv8.1-a",
        "armv8.2-a": "-march=armv8.2-a",
        "armv8.3-a": "-march=armv8.3-a",
        "armv8.4-a": "-march=armv8.4-a",
        "armv8.5-a": "-march=armv8.5-a",
        "armv8.6-a": "-march=armv8.6-a",
        "armv8.7-a": "-march=armv8.7-a",
        "armv8.8-a": "-march=armv8.8-a",
        "armv8.9-a": "-march=armv8.9-a",
        "armv8-r": "-march=armv8-r",
        "armv9-a": "-march=armv9-a",
        "armv9.1-a": "-march=armv9.1-a",
        "armv9.2-a": "-march=armv9.2-a",
        "armv9.3-a": "-march=armv9.3-a",
        "armv9.4-a": "-march=armv9.4-a",
    },
    "macos": {
        "x86_64": "-arch x86_64",
        "arm64": "-arch arm64",
    },
    "emscripten": {
        "wasm32": "",
    },
}


# Resolved settings of a C/C++/ObjC target, shared by its options.mk and rules.mk
@dataclass(frozen=True)
class CcSettings:
    source_root: Optional[str]  # common ancestor of the compiled sources
    sources: List[str]  # compiled sources, relative to source_root
    includes: List[str]
    build_includes: List[str]  # Swift dependencies' emitted header directories
    swift_headers: List[str]  # those headers, needed before anything compiles
    defines: List[str]
    cflags: str
    cxxflags: str
    lflags: str  # binaries only
    libs: List[str]  # dependency libraries in link order (binaries only)
    link_driver: str  # binaries only


# Resolved settings of a Swift target, shared by its options.mk and rules.mk
@dataclass(frozen=True)
class SwiftSettings:
    sources: List[str]  # workspace-relative
    flags: List[str]
    xcc_flags: List[str]
    module_search: List[str]
    dep_modules: List[str]  # dependencies' .swiftmodule files
    lflags: str  # binaries only
    libs: List[str]  # dependency libraries in link order (binaries only)


# Resolved settings of a metal_library, shared by its options.mk and rules.mk
@dataclass(frozen=True)
class MetalSettings:
    sdk: str
    flags: str
    source_root: Optional[str]  # common ancestor of the .metal sources
    sources: List[str]  # .metal sources, relative to source_root


# Writes a target's two makefiles into <package>/<target>/ under its arch/config
# directory:
#  - options.mk: every setting that decides how the target builds (flags,
#    defines, include paths, where its sources live). Objects depend on it.
#  - rules.mk: the object list and the rules; includes options.mk. Outputs depend
#    on both files.
# Each file is only rewritten when its contents change, so editing sources
# rebuilds just those objects plus the output, while changing any option rebuilds
# the whole target.
class TargetMk:
    def __init__(self, config, workspace, build_root, package, target):
        self.config = config
        self.workspace = workspace
        self.package = package
        self.target = target
        self.path = build_root.joinpath(
            mk_target_build_path(package=package, target=target)
        )
        self.options_path = build_root.joinpath(
            options_build_path(package=package, target=target)
        )

    def __call__(self):
        options = self.options_text()
        if options is not None:
            write_text_if_changed(self.options_path, options)
        write_text_if_changed(self.path, self.rules_text())

    @property
    def phony(self):
        return phony_target_name(package=self.package, target=self.target)

    @property
    def requires_linking(self):
        return isinstance(self.target, (CCBinary, SwiftBinary))

    @property
    def has_options(self):
        return not isinstance(self.target, AppleApplication)

    @property
    def out_path(self):
        if isinstance(self.target, CCLibrary):
            return cc_library_output_path(
                config=self.config, package=self.package, target=self.target
            )
        elif isinstance(self.target, CCBinary):
            return cc_binary_output_path(
                config=self.config, package=self.package, target=self.target
            )
        elif isinstance(self.target, AppleApplication):
            return apple_application_output_path(
                config=self.config, package=self.package, target=self.target
            )
        elif isinstance(self.target, MetalLibrary):
            return metal_library_output_path(
                config=self.config, package=self.package, target=self.target
            )
        elif isinstance(self.target, SwiftLibrary):
            return swift_library_output_path(
                config=self.config, package=self.package, target=self.target
            )
        elif isinstance(self.target, SwiftBinary):
            return swift_binary_output_path(
                config=self.config, package=self.package, target=self.target
            )
        else:
            raise RuntimeError(f"unknown target type {type(self.target)}")

    def var_name(self, prefix: str):
        return f"{prefix}__{flat_target_name(self.package.name, self.target.name)}"

    @property
    def options_ref(self):
        options = options_build_path(package=self.package, target=self.target)
        return f"$(BUILD_CONFIG_ROOT)/{options.as_posix()}"

    @property
    def rules_ref(self):
        rules = mk_target_build_path(package=self.package, target=self.target)
        return f"$(BUILD_CONFIG_ROOT)/{rules.as_posix()}"

    # The make path of a directory holding a target's sources
    def source_root_ref(self, path: str) -> str:
        rel = Path(os.path.relpath(path, self.workspace.root)).as_posix()
        return f"$(WORKSPACE_ROOT)/{rel}"

    # The contents of options.mk, or None for targets without options
    def options_text(self) -> Optional[str]:
        if not self.has_options:
            return None
        file = io.StringIO()
        file.writelines(["# Generated by Builderer\n", "\n"])
        if isinstance(self.target, (CCLibrary, CCBinary)):
            self._write_cc_options(file, self._cc_settings)
        elif isinstance(self.target, (SwiftLibrary, SwiftBinary)):
            self._write_swift_options(file, self._swift_settings)
        elif isinstance(self.target, MetalLibrary):
            self._write_metal_options(file, self._metal_settings)
        else:
            raise RuntimeError(f"unsupported target type {type(self.target)}")
        return file.getvalue()

    # The contents of rules.mk
    def rules_text(self) -> str:
        file = io.StringIO()
        file.writelines(["# Generated by Builderer\n", "\n"])
        if self.has_options:
            file.writelines(
                [
                    f"include {self.options_ref}\n",
                    "\n",
                    f"{self.var_name('OPTIONS')} := {self.options_ref}\n",
                ]
            )
        file.writelines(
            [
                f"{self.var_name('RULES')} := {self.rules_ref}\n",
                "\n",
                f"{self.phony}: {self.out_path}\n",
                "\n",
            ]
        )
        if isinstance(self.target, AppleApplication):
            self._write_apple_application_rules(file)
        elif isinstance(self.target, (CCLibrary, CCBinary)):
            self._write_cc_rules(file, self._cc_settings)
        elif isinstance(self.target, (SwiftLibrary, SwiftBinary)):
            self._write_swift_rules(file, self._swift_settings)
        elif isinstance(self.target, MetalLibrary):
            self._write_metal_rules(file, self._metal_settings)
        else:
            raise RuntimeError(f"unsupported target type {type(self.target)}")
        return file.getvalue()

    # All transitive dependencies (unique, reversed for link order)
    def _link_ordered_dependencies(self):
        return list(
            reversed(
                list(
                    self.workspace.all_dependencies(
                        package=self.package, target=self.target
                    )
                )
            )
        )

    #
    # C/C++/ObjC
    #

    @cached_property
    def _cc_settings(self) -> CcSettings:
        target = self.target
        dependencies = self._link_ordered_dependencies()
        cc_dependencies = [(p, t) for p, t in dependencies if isinstance(t, CCLibrary)]
        swift_dependencies = [
            (p, t) for p, t in dependencies if isinstance(t, SwiftLibrary)
        ]

        # compiled sources, relative to their common ancestor
        source_root, subpaths = object_subpaths(
            [
                src
                for src in resolve_conditionals(config=self.config, value=target.srcs)
                if file_kind(src) in C_FAMILY_KINDS
            ],
            self.workspace.root,
        )

        # private, public and dependency includes
        includes = list(
            resolve_conditionals(config=self.config, value=target.private_includes)
        )
        if isinstance(target, CCLibrary):
            includes.extend(
                resolve_conditionals(config=self.config, value=target.public_includes)
            )
        includes.extend(
            [
                i
                for _, dep_t in cc_dependencies
                for i in resolve_conditionals(
                    config=self.config, value=dep_t.public_includes
                )
            ]
        )

        # preprocessor defines
        defines = [
            *resolve_conditionals(config=self.config, value=target.private_defines)
        ]
        if isinstance(target, CCLibrary):
            defines.extend(
                resolve_conditionals(config=self.config, value=target.public_defines)
            )
        defines.extend(
            [
                define
                for _, dep_target in self.workspace.all_dependencies(
                    self.package, target
                )
                if isinstance(dep_target, CCLibrary)
                for define in resolve_conditionals(
                    config=self.config, value=dep_target.public_defines
                )
            ]
        )

        # architecture-specific compiler and linker flags
        archflags = PLATFORM_ARCH_FLAGS[self.config.platform][self.config.architecture]
        cflags = resolve_conditionals(config=self.config, value=target.c_flags)
        cxxflags = resolve_conditionals(config=self.config, value=target.cxx_flags)
        lflags = (
            resolve_conditionals(config=self.config, value=target.link_flags)
            if self.requires_linking
            else []
        )

        # dependency libraries to link, for binaries
        libs = []
        if self.requires_linking:
            libs = [
                cc_library_output_path(config=self.config, package=dep_p, target=dep_t)
                for dep_p, dep_t in cc_dependencies
                if not is_header_only_library(dep_t)
            ] + [
                swift_library_output_path(
                    config=self.config, package=dep_p, target=dep_t
                )
                for dep_p, dep_t in swift_dependencies
            ]

        swift_header_deps = [(p, t) for p, t in swift_dependencies if t.swift_header]
        return CcSettings(
            source_root=source_root,
            sources=list(subpaths.values()),
            includes=includes,
            build_includes=[swift_header_dir(p, t) for p, t in swift_header_deps],
            swift_headers=[
                f"{swift_header_dir(p, t)}/{t.swift_header}"
                for p, t in swift_header_deps
            ],
            defines=defines,
            cflags=f"{archflags} {' '.join(cflags)}",
            cxxflags=f"{archflags} {' '.join(cxxflags)}",
            lflags=f"{archflags} {' '.join(lflags)}",
            libs=libs,
            # When linking against any SwiftLibrary, drive the link with swiftc so
            # Swift runtime + rpaths are handled automatically.
            link_driver="$(SWIFTC)" if swift_dependencies else "$(CCLD)",
        )

    def _write_cc_options(self, file: TextIO, settings: CcSettings):
        includes_var = self.var_name("INCLUDES")
        build_includes_var = self.var_name("BUILD_INCLUDES")
        defines_var = self.var_name("DEFINES")
        cflags_var = self.var_name("CFLAGS")
        cxxflags_var = self.var_name("CXXFLAGS")

        # Where the sources live: when it moves (e.g. a repository fetched into a
        # new sandbox) the objects keep their paths but must rebuild
        if settings.source_root:
            file.write(
                f"{self.var_name('SRC_ROOT')} := "
                f"{self.source_root_ref(settings.source_root)}\n\n"
            )
        file.writelines(
            [
                f"{includes_var} :=",
                *[f" \\\n  {i}" for i in settings.includes],
                "\n\n",
                f"{build_includes_var} :=",
                *[f" \\\n  {i}" for i in settings.build_includes],
                "\n\n",
                f"{defines_var} := {' '.join(settings.defines)}\n",
                "\n",
                f"{cflags_var}   := {settings.cflags}\n",
                f"{cxxflags_var} := {settings.cxxflags}\n",
                "\n",
            ]
        )
        if self.requires_linking:
            file.write(f"{self.var_name('LFLAGS')}   := {settings.lflags}\n\n")

        # Compile commands, expanded for each object at recipe time
        common_flags = (
            f"$(addprefix -I$(WORKSPACE_ROOT)/,$({includes_var})) "
            f"$(addprefix -I,$({build_includes_var})) "
            f"$(addprefix -D,$({defines_var}))"
        )
        file.writelines(
            [
                f"{self.var_name('CC_COMPILE')} = $(CC) -MT $@ -MMD -MP -MF $(@:.o=.d) $({cflags_var}) {common_flags} -c $< -o $@\n",
                f"{self.var_name('CXX_COMPILE')} = $(CXX) -MT $@ -MMD -MP -MF $(@:.o=.d) $({cxxflags_var}) {common_flags} -c $< -o $@\n",
            ]
        )

    def _write_cc_rules(self, file: TextIO, settings: CcSettings):
        options_var = self.var_name("OPTIONS")
        rules_var = self.var_name("RULES")
        obj_dir_var = self.var_name("OBJ_DIR")
        objs_var = self.var_name("OBJS")
        deps_var = self.var_name("DEPS")

        # objects in this target's intermediates directory, with their .d files
        objects = [f"$({obj_dir_var})/{src}.o" for src in settings.sources]
        file.writelines(
            [
                f"{obj_dir_var} := {target_obj_dir(self.package, self.target)}\n",
                f"{objs_var} :=",
                *[f" \\\n  {obj}" for obj in objects],
                "\n",
                f"{deps_var} := $({objs_var}:.o=.d)\n",
                "\n",
                f"-include $({deps_var})\n",
                "\n",
            ]
        )

        # output target, rebuilt when the object list or any option changes
        if isinstance(self.target, CCLibrary):
            file.writelines(
                [
                    f"{self.out_path}: $({objs_var}) $({options_var}) $({rules_var})\n",
                    f"\t@$(ECHO) Archiving $@\n",
                    f"\t@$(MKDIR) $(dir $@)\n",
                    f"\t@$(RM) $@\n",
                    f"\t@$(AR) rcS $@ $({objs_var})\n",
                    f"\t@$(RANLIB) $@\n",
                    "\n",
                ]
            )
        elif isinstance(self.target, CCBinary):
            libs = " ".join(settings.libs)
            file.writelines(
                [
                    f"{self.out_path}: $({objs_var}) {libs} $({options_var}) $({rules_var})\n",
                    f"\t@$(ECHO) Linking $@\n",
                    f"\t@$(MKDIR) $(dir $@)\n",
                    f"\t@{settings.link_driver} $({objs_var}) {libs} $({self.var_name('LFLAGS')}) -o $@\n",
                    "\n",
                ]
            )
        else:
            raise RuntimeError(f"unknown target type {type(self.target)}")

        # The Swift-emitted headers (if any) must exist before any cc object file
        # that #includes them is built. Use an order-only prereq so this doesn't
        # force unnecessary rebuilds when headers change (header changes invalidate
        # the .swiftmodule sentinel, which propagates via the swift compile rule).
        if settings.swift_headers:
            file.write(f"$({objs_var}): | {' '.join(settings.swift_headers)}\n\n")

        # One rule per object; its source is the first prerequisite ($<)
        for src, obj in zip(settings.sources, objects):
            kind = file_kind(src)
            assert kind is not None, src  # only C-family sources get objects
            compile_var = self.var_name(COMPILE_COMMANDS[kind])
            file.writelines(
                [
                    f"{obj}: $({self.var_name('SRC_ROOT')})/{src} $({options_var})\n",
                    f"\t@$(ECHO) Compiling $(notdir $<)\n",
                    f"\t@$(MKDIR) $(dir $@)\n",
                    f"\t@$({compile_var})\n",
                    "\n",
                ]
            )

    #
    # Swift
    #

    @cached_property
    def _swift_settings(self) -> SwiftSettings:
        target = self.target
        is_library = isinstance(target, SwiftLibrary)
        dependencies = self._link_ordered_dependencies()
        cc_dependencies = [(p, t) for p, t in dependencies if isinstance(t, CCLibrary)]
        swift_dependencies = [
            (p, t) for p, t in dependencies if isinstance(t, SwiftLibrary)
        ]
        swift_cc_modules = [
            (p, t) for p, t in dependencies if isinstance(t, SwiftCcModule)
        ]

        # Swift flags (swiftc uses -target, not -arch)
        swift_archflags = SWIFT_PLATFORM_ARCH_FLAGS.get(self.config.platform, {}).get(
            self.config.architecture, ""
        )
        flags = [
            swift_archflags,
            "-module-name",
            target.name,
            "-whole-module-optimization",
            "-emit-object",
        ]
        if is_library:
            flags += [
                "-emit-module",
                "-emit-module-path",
                f"$({self.var_name('SWIFTMODULE')})",
            ]
            if target.swift_header:
                emit_flag = (
                    "-emit-clang-header-path"
                    if target.cxx_interop
                    else "-emit-objc-header-path"
                )
                flags += [emit_flag, f"$({self.var_name('SWIFTHEADER')})"]
        if target.cxx_interop:
            flags += ["-cxx-interoperability-mode=default"]
        flags += resolve_conditionals(config=self.config, value=target.swift_flags)

        # -Xcc flags: modulemaps from swift_cc_module deps + include/define from cc_library deps
        xcc_flags: List[str] = []
        for _, ccmod_t in swift_cc_modules:
            for modmap_abs in ccmod_t.module_maps:
                modmap_rel = Path(
                    os.path.relpath(modmap_abs, self.workspace.root)
                ).as_posix()
                xcc_flags += [
                    "-Xcc",
                    f"-fmodule-map-file=$(WORKSPACE_ROOT)/{modmap_rel}",
                ]
        # All transitive cc_library deps' public includes/defines become importable surface
        # for the Swift compile (via -Xcc to the embedded clang).
        for _, cc_dep in cc_dependencies:
            for inc in resolve_conditionals(
                config=self.config, value=cc_dep.public_includes
            ):
                xcc_flags += ["-Xcc", f"-I$(WORKSPACE_ROOT)/{inc}"]
            for d in resolve_conditionals(
                config=self.config, value=cc_dep.public_defines
            ):
                xcc_flags += ["-Xcc", f"-D{d}"]

        # -I search paths for dep swift_library .swiftmodule directories
        module_search: List[str] = []
        for sw_p, sw_dep in swift_dependencies:
            module_search += ["-I", swift_module_dir(sw_p, sw_dep)]

        # dependency libraries to link, for binaries
        libs = []
        lflags = ""
        if not is_library:
            libs = [
                cc_library_output_path(config=self.config, package=dep_p, target=dep_t)
                for dep_p, dep_t in cc_dependencies
                if not is_header_only_library(dep_t)
            ] + [
                swift_library_output_path(
                    config=self.config, package=dep_p, target=dep_t
                )
                for dep_p, dep_t in swift_dependencies
            ]
            user_link_flags = resolve_conditionals(
                config=self.config, value=target.link_flags
            )
            lflags = f"{swift_archflags} {' '.join(user_link_flags)}"

        return SwiftSettings(
            # workspace-relative posix paths, joined with WORKSPACE_ROOT at use
            sources=[
                Path(os.path.relpath(src, self.workspace.root)).as_posix()
                for src in resolve_conditionals(config=self.config, value=target.srcs)
                if file_kind(src) is FileKind.SWIFT
            ],
            flags=flags,
            xcc_flags=xcc_flags,
            module_search=module_search,
            dep_modules=[swift_module_path(p, t) for p, t in swift_dependencies],
            lflags=lflags,
            libs=libs,
        )

    def _write_swift_options(self, file: TextIO, settings: SwiftSettings):
        file.writelines(
            [
                f"{self.var_name('SWIFTFLAGS')} := {' '.join(settings.flags)}\n\n",
                f"{self.var_name('SWIFT_XCC')} := {' '.join(settings.xcc_flags)}\n\n",
                f"{self.var_name('SWIFT_MODULE_I')} := {' '.join(settings.module_search)}\n",
            ]
        )
        if self.requires_linking:
            file.write(f"\n{self.var_name('LFLAGS')} := {settings.lflags}\n")

    def _write_swift_rules(self, file: TextIO, settings: SwiftSettings):
        target = self.target
        is_library = isinstance(target, SwiftLibrary)
        srcs_var = self.var_name("SWIFT_SRCS")
        obj_var = self.var_name("SWIFT_OBJ")
        module_var = self.var_name("SWIFTMODULE")
        header_var = self.var_name("SWIFTHEADER")
        options_var = self.var_name("OPTIONS")
        rules_var = self.var_name("RULES")

        file.writelines(
            [
                f"{srcs_var} :=",
                *[f" \\\n  {s}" for s in settings.sources],
                "\n\n",
            ]
        )

        # output paths, in this target's intermediates directory
        obj_dir = target_obj_dir(self.package, target)
        file.write(f"{obj_var} := {obj_dir}/{target.name}.swift.o\n")
        if is_library:
            file.write(f"{module_var} := {swift_module_path(self.package, target)}\n")
            if target.swift_header:
                file.write(
                    f"{header_var} := {swift_header_dir(self.package, target)}/{target.swift_header}\n"
                )
        file.write("\n")

        # Output / link rule, rebuilt when the module or any option changes
        if is_library:
            file.writelines(
                [
                    f"{self.out_path}: $({obj_var}) $({options_var}) $({rules_var})\n",
                    f"\t@$(ECHO) Archiving $@\n",
                    f"\t@$(MKDIR) $(dir $@)\n",
                    f"\t@$(RM) $@\n",
                    f"\t@$(AR) rcS $@ $({obj_var})\n",
                    f"\t@$(RANLIB) $@\n",
                    "\n",
                ]
            )
        else:
            libs = " ".join(settings.libs)
            file.writelines(
                [
                    f"{self.out_path}: $({obj_var}) {libs} $({options_var}) $({rules_var})\n",
                    f"\t@$(ECHO) Linking $@\n",
                    f"\t@$(MKDIR) $(dir $@)\n",
                    f"\t@$(SWIFTC) $({obj_var}) {libs} $({self.var_name('LFLAGS')}) -o $@\n",
                    "\n",
                ]
            )

        # Swift compile rule: produces .o (+ .swiftmodule and emitted header for libraries).
        # Prereqs: source files + dep .swiftmodules (so make orders swift→swift correctly),
        # plus both makefiles: the module compiles whole, so a changed source list
        # (in rules.mk) rebuilds it just like a changed option.
        compile_outputs = [f"$({obj_var})"]
        if is_library:
            compile_outputs.append(f"$({module_var})")
            if target.swift_header:
                compile_outputs.append(f"$({header_var})")
        compile_prereqs = [
            f"$(addprefix $(WORKSPACE_ROOT)/,$({srcs_var}))",
            f"$({options_var})",
            f"$({rules_var})",
            *settings.dep_modules,
        ]
        file.write(f"{' '.join(compile_outputs)}: {' '.join(compile_prereqs)}\n")
        file.write(f"\t@$(ECHO) Compiling Swift module {target.name}\n")
        for out_ref in compile_outputs:
            file.write(f"\t@$(MKDIR) $(dir {out_ref})\n")
        file.write(
            f"\t@$(SWIFTC) $({self.var_name('SWIFTFLAGS')}) $({self.var_name('SWIFT_XCC')})"
            f" $({self.var_name('SWIFT_MODULE_I')})"
            f" -o $({obj_var})"
            f" $(addprefix $(WORKSPACE_ROOT)/,$({srcs_var}))\n\n"
        )

    #
    # Metal
    #

    @cached_property
    def _metal_settings(self) -> MetalSettings:
        target = self.target
        if self.config.platform not in METAL_PLATFORM:
            raise ValueError(
                f"metal_library '{target.name}' is not supported on platform "
                f"'{self.config.platform}' (Metal is Apple-only); supported: "
                f"{sorted(METAL_PLATFORM)}"
            )
        sdk, triple = METAL_PLATFORM[self.config.platform]
        source_root, subpaths = object_subpaths(
            [
                src
                for src in resolve_conditionals(config=self.config, value=target.srcs)
                if file_kind(src) is FileKind.METAL
            ],
            self.workspace.root,
        )
        user_flags = resolve_conditionals(config=self.config, value=target.metal_flags)
        return MetalSettings(
            sdk=sdk,
            flags=f"-target {triple} {' '.join(user_flags)}",
            source_root=source_root,
            sources=list(subpaths.values()),
        )

    def _write_metal_options(self, file: TextIO, settings: MetalSettings):
        if settings.source_root:
            file.write(
                f"{self.var_name('SRC_ROOT')} := "
                f"{self.source_root_ref(settings.source_root)}\n\n"
            )
        file.write(f"{self.var_name('METALFLAGS')} := {settings.flags}\n")

    def _write_metal_rules(self, file: TextIO, settings: MetalSettings):
        air_var = self.var_name("METAL_AIR")
        options_var = self.var_name("OPTIONS")
        rules_var = self.var_name("RULES")

        # One .air per source in this target's intermediates directory, at the
        # source's path relative to the sources' common ancestor
        obj_dir = target_obj_dir(self.package, self.target)
        airs = [f"{obj_dir}/{src}.air" for src in settings.sources]
        file.writelines(
            [
                f"{air_var} :=",
                *[f" \\\n  {air}" for air in airs],
                "\n\n",
            ]
        )

        # Compile rule: .metal -> .air
        for src, air in zip(settings.sources, airs):
            file.writelines(
                [
                    f"{air}: $({self.var_name('SRC_ROOT')})/{src} $({options_var})\n",
                    f"\t@$(ECHO) Compiling Metal {Path(src).name}\n",
                    f"\t@$(MKDIR) $(dir $@)\n",
                    f"\t@xcrun -sdk {settings.sdk} metal -c $({self.var_name('METALFLAGS')}) -o $@ $<\n",
                    "\n",
                ]
            )

        # Link rule: all .air -> the bare <target.name>.metallib file (out_path).
        # The consuming app copies this file to its resources root; whether it
        # becomes the default library (makeDefaultLibrary()) or a URL-loaded
        # library is determined purely by its filename (the target name).
        file.writelines(
            [
                f"{self.out_path}: $({air_var}) $({options_var}) $({rules_var})\n",
                f"\t@$(ECHO) Linking Metal library $@\n",
                f"\t@$(MKDIR) $(dir $@)\n",
                f"\t@xcrun -sdk {settings.sdk} metallib -o $@ $({air_var})\n",
                "\n",
            ]
        )

    #
    # Apple application bundles
    #

    def _write_apple_application_rules(self, file: TextIO):
        binary_package, binary_target = self.target.resolve_binary_target(
            self.workspace, self.package
        )
        binary_output = cc_binary_output_path_workspace(
            config=self.config,
            workspace=self.workspace,
            package=binary_package,
            target=binary_target,
        )
        binary_path = Path(
            os.path.relpath(binary_output, self.workspace.root)
        ).as_posix()
        info_plist = resolve_conditionals(
            config=self.config, value=self.target.info_plist
        )
        validate_resolved_info_plist(self.target.name, info_plist)
        executable_name = str(info_plist.get("CFBundleExecutable", binary_target.name))
        plist_xml_lines = plist_dict_to_xml_text(info_plist).splitlines()
        plist_write_lines = [
            (
                f"\t@$(ECHO) '{line}' > $@/Contents/Info.plist\n"
                if idx == 0
                else f"\t@$(ECHO) '{line}' >> $@/Contents/Info.plist\n"
            )
            for idx, line in enumerate(plist_xml_lines)
        ]
        # Merged (src, dst) resource pairs from the app's file_groups; src is made
        # workspace-relative for the $(WORKSPACE_ROOT)/... reference, dst is the
        # in-bundle path (may include subdirectories) relative to the resources dir.
        resource_pairs = [
            (Path(os.path.relpath(src, self.workspace.root)).as_posix(), dst)
            for src, dst in self.target.resolve_resources(self.workspace, self.package)
        ]
        # metal_library deps: each produces a bare <target.name>.metallib file that
        # gets copied into the app's resources dir under that filename.
        # metal_library_output_path already carries the $(WORKSPACE_ROOT)/... prefix.
        metal_libs = [
            (
                metal_library_output_path(
                    config=self.config, package=ml_pkg, target=ml_target
                ),
                f"{ml_target.name}.metallib",
            )
            for ml_pkg, ml_target in self.target.resolve_metal_library_targets(
                self.workspace, self.package
            )
        ]
        # The platform resources dir (macOS: Contents/Resources; flat bundles: root).
        res_dir = apple_bundle_resource_dir(self.config.platform)
        dst_prefix = f"$@/{res_dir}" if res_dir else "$@"
        # The bundle's contents (Info.plist, resource list) live in rules.mk, so it
        # repackages when that file changes
        file.writelines(
            [
                f"{self.out_path}: $(WORKSPACE_ROOT)/{binary_path}",
                *[f" $(WORKSPACE_ROOT)/{src}" for src, _ in resource_pairs],
                *[f" {metallib_path}" for metallib_path, _ in metal_libs],
                f" $({self.var_name('RULES')})",
                "\n",
                "\t@$(ECHO) Packaging $@\n",
                "\t@rm -rf $@\n",
                "\t@$(MKDIR) $@/Contents/MacOS\n",
                f"\t@$(MKDIR) {dst_prefix}\n",
                f"\t@$(CP) $(WORKSPACE_ROOT)/{binary_path} $@/Contents/MacOS/{executable_name}\n",
                *plist_write_lines,
                "\t@printf 'APPL????\\n' > $@/Contents/PkgInfo\n",
            ]
        )
        # Copy each file_group resource to its destination, preserving structure
        # (dst may include subdirectories) relative to the resources dir.
        for src, dst in resource_pairs:
            dst_dir = dst.rsplit("/", 1)[0] if "/" in dst else ""
            if dst_dir:
                file.write(f"\t@$(MKDIR) {dst_prefix}/{dst_dir}\n")
            file.write(f"\t@$(CP) $(WORKSPACE_ROOT)/{src} {dst_prefix}/{dst}\n")
        # Embed each metal_library's <target.name>.metallib into the app's platform
        # resources dir. A dep named "default" yields default.metallib at the
        # resources root (makeDefaultLibrary()); others are URL-loaded by name.
        for metallib_path, metallib_basename in metal_libs:
            file.write(f"\t@$(CP) {metallib_path} {dst_prefix}/{metallib_basename}\n")
        file.write("\n")
