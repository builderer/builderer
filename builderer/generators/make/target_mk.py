import os

from pathlib import Path
from typing import TextIO
from xml.sax.saxutils import escape

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

CC_EXTS = (
    ".c",
    ".m",
)

CXX_EXTS = (
    ".cc",
    ".cpp",
    ".cxx",
    ".mm",
)

SWIFT_EXTS = (".swift",)

COMPILE_EXTS = frozenset(CC_EXTS + CXX_EXTS)


def _plist_value_to_xml_lines(value, indent: str = "  ") -> list[str]:
    if isinstance(value, str):
        return [f"{indent}<string>{escape(value)}</string>"]
    elif isinstance(value, bool):
        return [f"{indent}<{str(value).lower()}/>"]
    elif isinstance(value, int):
        return [f"{indent}<integer>{value}</integer>"]
    elif isinstance(value, float):
        return [f"{indent}<real>{value}</real>"]
    elif isinstance(value, list):
        lines = [f"{indent}<array>"]
        for item in value:
            lines.extend(_plist_value_to_xml_lines(item, indent + "  "))
        lines.append(f"{indent}</array>")
        return lines
    elif isinstance(value, dict):
        lines = [f"{indent}<dict>"]
        for key in sorted(value.keys()):
            lines.append(f"{indent}  <key>{escape(str(key))}</key>")
            lines.extend(_plist_value_to_xml_lines(value[key], indent + "  "))
        lines.append(f"{indent}</dict>")
        return lines
    else:
        raise ValueError(f"unsupported info_plist value type: {type(value).__name__}")


def _plist_dict_to_xml_text(info_plist: dict) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
        '<plist version="1.0">',
        "<dict>",
    ]
    for key in sorted(info_plist.keys()):
        lines.append(f"  <key>{escape(str(key))}</key>")
        lines.extend(_plist_value_to_xml_lines(info_plist[key], "  "))
    lines.extend(["</dict>", "</plist>"])
    return "\n".join(lines)


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

METAL_EXTS = (".metal",)


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


class TargetMk:
    def __init__(self, config, workspace, build_root, package, target):
        self.config = config
        self.workspace = workspace
        self.package = package
        self.target = target
        self.path = build_root.joinpath(
            mk_target_build_path(package=package, target=target)
        )

    @property
    def phony(self):
        return phony_target_name(package=self.package, target=self.target)

    @property
    def requires_linking(self):
        return isinstance(self.target, (CCBinary, SwiftBinary))

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
        return f"{prefix}__{self.package.name.replace('/','_')}__{self.target.name}"

    def __call__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as file:
            self._write_makefile(file)

    def _write_makefile(self, file: TextIO):
        if isinstance(self.target, AppleApplication):
            self._write_apple_application_makefile(file)
        elif isinstance(self.target, (CCLibrary, CCBinary)):
            self._write_cc_makefile(file)
        elif isinstance(self.target, (SwiftLibrary, SwiftBinary)):
            self._write_swift_makefile(file)
        elif isinstance(self.target, MetalLibrary):
            self._write_metal_makefile(file)
        else:
            raise RuntimeError(f"unsupported target type {type(self.target)}")

    def _write_cc_makefile(self, file: TextIO):
        # pick some variable names...
        includes_var = self.var_name("INCLUDES")
        build_includes_var = self.var_name("BUILD_INCLUDES")
        defines_var = self.var_name("DEFINES")
        cflags_var = self.var_name("CFLAGS")
        cxxflags_var = self.var_name("CXXFLAGS")
        lflags_var = self.var_name("LFLAGS")
        srcs_var = self.var_name("SRCS")
        objs_var = self.var_name("OBJS")
        deps_var = self.var_name("DEPS")

        # All transitive dependencies (unique, reversed for link order)
        all_dep_list = list(
            reversed(
                list(
                    self.workspace.all_dependencies(
                        package=self.package, target=self.target
                    )
                )
            )
        )
        all_dependencies = [(p, t) for p, t in all_dep_list if isinstance(t, CCLibrary)]
        swift_dependencies = [
            (p, t) for p, t in all_dep_list if isinstance(t, SwiftLibrary)
        ]

        # header
        file.writelines(
            [
                f"# Generated by Builderer\n",
                "\n",
            ]
        )

        # Phony package/target name
        file.writelines(
            [
                f"{self.phony}: {self.out_path}\n",
                "\n",
            ]
        )

        # source files
        file.writelines(
            [
                f"{srcs_var} :=",
                *[
                    f" \\\n  {Path(os.path.relpath(src, self.workspace.root)).as_posix()}"
                    for src in resolve_conditionals(
                        config=self.config, value=self.target.srcs
                    )
                    if os.path.splitext(src)[-1] in COMPILE_EXTS
                ],
                "\n\n",
            ]
        )

        # private includes
        includes = list(
            resolve_conditionals(config=self.config, value=self.target.private_includes)
        )
        # public includes
        if isinstance(self.target, CCLibrary):
            includes.extend(
                resolve_conditionals(
                    config=self.config, value=self.target.public_includes
                )
            )
        # dependency includes
        includes.extend(
            [
                i
                for _, dep_t in all_dependencies
                for i in resolve_conditionals(
                    config=self.config, value=dep_t.public_includes
                )
            ]
        )
        file.writelines(
            [
                f"{includes_var} :=",
                *[f" \\\n  {i}" for i in includes],
                "\n\n",
            ]
        )

        # build-tree includes: emitted Swift headers from SwiftLibrary deps (when swift_header is set).
        # These are relative to $(BUILD_CONFIG_ROOT), not $(WORKSPACE_ROOT).
        build_includes = [
            swift_header_dir(dep_p, dep_t)
            for dep_p, dep_t in swift_dependencies
            if dep_t.swift_header
        ]
        file.writelines(
            [
                f"{build_includes_var} :=",
                *[f" \\\n  {i}" for i in build_includes],
                "\n\n",
            ]
        )

        # preprocessor defines
        defines = [
            *resolve_conditionals(config=self.config, value=self.target.private_defines)
        ]
        if isinstance(self.target, CCLibrary):
            defines.extend(
                resolve_conditionals(
                    config=self.config, value=self.target.public_defines
                )
            )
        defines.extend(
            [
                define
                for _, dep_target in self.workspace.all_dependencies(
                    self.package, self.target
                )
                if isinstance(dep_target, CCLibrary)
                for define in resolve_conditionals(
                    config=self.config, value=dep_target.public_defines
                )
            ]
        )
        file.writelines(
            [
                f"{defines_var} := {' '.join(defines)}\n",
                "\n",
            ]
        )

        # get architecture-specific compiler and linker flags...
        archflags = PLATFORM_ARCH_FLAGS[self.config.platform][self.config.architecture]

        # compiler flags
        cflags = resolve_conditionals(config=self.config, value=self.target.c_flags)
        cxxflags = resolve_conditionals(config=self.config, value=self.target.cxx_flags)
        file.writelines(
            [
                f"{cflags_var}   := {archflags} {' '.join(cflags)}\n",
                f"{cxxflags_var} := {archflags} {' '.join(cxxflags)}\n",
                "\n",
            ]
        )

        # linker flags
        if self.requires_linking:
            lflags = [
                *resolve_conditionals(config=self.config, value=self.target.link_flags),
            ]
            file.writelines(
                [
                    f"{lflags_var}   := {archflags} {' '.join(lflags)}\n",
                    "\n",
                ]
            )

        # object/dependency files
        file.writelines(
            [
                f"{objs_var} := $(patsubst %,$(OBJS_ROOT)/%.o,$({srcs_var}))\n",
                f"{deps_var} := $(addsuffix .d,$({objs_var}))\n",
                "\n",
            ]
        )

        # Include deps files if available
        file.writelines(
            [
                f"-include $({deps_var})\n",
                "\n",
            ]
        )

        # output target...
        if isinstance(self.target, CCLibrary):
            file.writelines(
                [
                    f"{self.out_path}: $({objs_var})\n",
                    f"\t@$(ECHO) Archiving $@\n" f"\t@$(MKDIR) $(dir $@)\n",
                    f"\t@$(RM) $@\n",
                    f"\t@$(AR) rcS $@ $^\n",
                    f"\t@$(RANLIB) $@\n",
                    "\n",
                ]
            )
        elif isinstance(self.target, CCBinary):
            dep_libs = [
                cc_library_output_path(config=self.config, package=dep_p, target=dep_t)
                for dep_p, dep_t in all_dependencies
                if not is_header_only_library(dep_t)
            ]
            swift_dep_libs = [
                swift_library_output_path(
                    config=self.config, package=dep_p, target=dep_t
                )
                for dep_p, dep_t in swift_dependencies
            ]
            # When linking against any SwiftLibrary, drive the link with swiftc so
            # Swift runtime + rpaths are handled automatically.
            link_driver = "$(SWIFTC)" if swift_dependencies else "$(CCLD)"
            file.writelines(
                [
                    f"{self.out_path}: $({objs_var}) {' '.join(dep_libs + swift_dep_libs)}\n",
                    f"\t@$(ECHO) Linking $@\n" f"\t@$(MKDIR) $(dir $@)\n",
                    f"\t@{link_driver} $^ $({lflags_var}) -o $@\n",
                    "\n",
                ]
            )
        else:
            raise RuntimeError(f"unknown target type {type(self.target)}")

        # The Swift-emitted headers (if any) must exist before any cc object file
        # that #includes them is built. Use an order-only prereq so this doesn't
        # force unnecessary rebuilds when headers change (header changes invalidate
        # the .swiftmodule sentinel, which propagates via the swift compile rule).
        swift_header_paths = [
            f"$(BUILD_CONFIG_ROOT)/{swift_header_dir(dep_p, dep_t)}/{dep_t.swift_header}"
            for dep_p, dep_t in swift_dependencies
            if dep_t.swift_header
        ]
        if swift_header_paths:
            file.write(f"$({objs_var}): | {' '.join(swift_header_paths)}\n\n")

        # .c rule
        for ext in CC_EXTS:
            file.writelines(
                [
                    f"$(filter %{ext}.o,$({objs_var})): $(OBJS_ROOT)/%.o: $(WORKSPACE_ROOT)/%\n",
                    f"\t@$(ECHO) Compiling $(notdir $<)\n",
                    f"\t@$(MKDIR) $(dir $@)\n",
                    f"\t@$(CC) -MT $@ -MMD -MP -MF $@.d $({cflags_var}) $(addprefix -I$(WORKSPACE_ROOT)/,$({includes_var})) $(addprefix -I$(BUILD_CONFIG_ROOT)/,$({build_includes_var})) $(addprefix -D,$({defines_var})) -c $< -o $@\n",
                    "\n",
                ]
            )

        # .cpp rule
        for ext in CXX_EXTS:
            file.writelines(
                [
                    f"$(filter %{ext}.o,$({objs_var})): $(OBJS_ROOT)/%.o: $(WORKSPACE_ROOT)/%\n",
                    f"\t@$(ECHO) Compiling $(notdir $<)\n",
                    f"\t@$(MKDIR) $(dir $@)\n",
                    f"\t@$(CXX) -MT $@ -MMD -MP -MF $@.d $({cxxflags_var}) $(addprefix -I$(WORKSPACE_ROOT)/,$({includes_var})) $(addprefix -I$(BUILD_CONFIG_ROOT)/,$({build_includes_var})) $(addprefix -D,$({defines_var})) -c $< -o $@\n",
                    "\n",
                ]
            )

    def _write_swift_makefile(self, file: TextIO):
        is_library = isinstance(self.target, SwiftLibrary)
        target = self.target

        srcs_var = self.var_name("SWIFT_SRCS")
        flags_var = self.var_name("SWIFTFLAGS")
        xcc_var = self.var_name("SWIFT_XCC")
        modulesearch_var = self.var_name("SWIFT_MODULE_I")
        obj_var = self.var_name("SWIFT_OBJ")
        module_var = self.var_name("SWIFTMODULE")
        header_var = self.var_name("SWIFTHEADER")
        lflags_var = self.var_name("LFLAGS")

        all_dep_list = list(
            reversed(
                list(
                    self.workspace.all_dependencies(package=self.package, target=target)
                )
            )
        )
        cc_dependencies = [(p, t) for p, t in all_dep_list if isinstance(t, CCLibrary)]
        swift_dependencies = [
            (p, t) for p, t in all_dep_list if isinstance(t, SwiftLibrary)
        ]
        swift_cc_modules = [
            (p, t) for p, t in all_dep_list if isinstance(t, SwiftCcModule)
        ]

        file.writelines(["# Generated by Builderer\n", "\n"])
        file.writelines([f"{self.phony}: {self.out_path}\n", "\n"])

        # source files (workspace-relative posix paths, joined with WORKSPACE_ROOT at use)
        swift_srcs = [
            Path(os.path.relpath(src, self.workspace.root)).as_posix()
            for src in resolve_conditionals(config=self.config, value=target.srcs)
            if os.path.splitext(src)[-1] in SWIFT_EXTS
        ]
        file.writelines(
            [
                f"{srcs_var} :=",
                *[f" \\\n  {s}" for s in swift_srcs],
                "\n\n",
            ]
        )

        # output paths
        obj_subpath = f".obj/{self.package.name}/{target.name}.swift.o"
        file.write(f"{obj_var} := $(BUILD_CONFIG_ROOT)/{obj_subpath}\n")
        if is_library:
            file.write(
                f"{module_var} := $(BUILD_CONFIG_ROOT)/{swift_module_path(self.package, target)}\n"
            )
            if target.swift_header:
                file.write(
                    f"{header_var} := $(BUILD_CONFIG_ROOT)/{swift_header_dir(self.package, target)}/{target.swift_header}\n"
                )
        file.write("\n")

        # Swift flags (swiftc uses -target, not -arch)
        swift_archflags = SWIFT_PLATFORM_ARCH_FLAGS.get(self.config.platform, {}).get(
            self.config.architecture, ""
        )
        user_swift_flags = list(
            resolve_conditionals(config=self.config, value=target.swift_flags)
        )
        flags = [
            swift_archflags,
            "-module-name",
            target.name,
            "-whole-module-optimization",
            "-emit-object",
        ]
        if is_library:
            flags += ["-emit-module", "-emit-module-path", f"$({module_var})"]
            if target.swift_header:
                emit_flag = (
                    "-emit-clang-header-path"
                    if target.cxx_interop
                    else "-emit-objc-header-path"
                )
                flags += [emit_flag, f"$({header_var})"]
        if target.cxx_interop:
            flags += ["-cxx-interoperability-mode=default"]
        flags += user_swift_flags
        file.write(f"{flags_var} := {' '.join(flags)}\n\n")

        # -Xcc flags: modulemaps from swift_cc_module deps + include/define from cc_library deps
        xcc_flags: list[str] = []
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
        file.write(f"{xcc_var} := {' '.join(xcc_flags)}\n\n")

        # -I search paths for dep swift_library .swiftmodule directories
        module_search = []
        for sw_p, sw_dep in swift_dependencies:
            module_search += [
                "-I",
                f"$(BUILD_CONFIG_ROOT)/{swift_module_dir(sw_p, sw_dep)}",
            ]
        file.write(f"{modulesearch_var} := {' '.join(module_search)}\n\n")

        # Output / link rule
        if is_library:
            file.writelines(
                [
                    f"{self.out_path}: $({obj_var})\n",
                    f"\t@$(ECHO) Archiving $@\n",
                    f"\t@$(MKDIR) $(dir $@)\n",
                    f"\t@$(RM) $@\n",
                    f"\t@$(AR) rcS $@ $^\n",
                    f"\t@$(RANLIB) $@\n",
                    "\n",
                ]
            )
        else:
            dep_libs = [
                cc_library_output_path(config=self.config, package=dep_p, target=dep_t)
                for dep_p, dep_t in cc_dependencies
                if not is_header_only_library(dep_t)
            ]
            swift_dep_libs = [
                swift_library_output_path(
                    config=self.config, package=dep_p, target=dep_t
                )
                for dep_p, dep_t in swift_dependencies
            ]
            user_link_flags = list(
                resolve_conditionals(config=self.config, value=target.link_flags)
            )
            file.write(
                f"{lflags_var} := {swift_archflags} {' '.join(user_link_flags)}\n\n"
            )
            file.writelines(
                [
                    f"{self.out_path}: $({obj_var}) {' '.join(dep_libs + swift_dep_libs)}\n",
                    f"\t@$(ECHO) Linking $@\n",
                    f"\t@$(MKDIR) $(dir $@)\n",
                    f"\t@$(SWIFTC) $^ $({lflags_var}) -o $@\n",
                    "\n",
                ]
            )

        # Swift compile rule: produces .o (+ .swiftmodule and emitted header for libraries).
        # Prereqs: source files + dep .swiftmodules (so make orders swift→swift correctly).
        compile_outputs = [f"$({obj_var})"]
        if is_library:
            compile_outputs.append(f"$({module_var})")
            if target.swift_header:
                compile_outputs.append(f"$({header_var})")
        compile_prereqs = [f"$(addprefix $(WORKSPACE_ROOT)/,$({srcs_var}))"]
        for dep_p, dep_t in swift_dependencies:
            compile_prereqs.append(
                f"$(BUILD_CONFIG_ROOT)/{swift_module_path(dep_p, dep_t)}"
            )
        file.write(f"{' '.join(compile_outputs)}: {' '.join(compile_prereqs)}\n")
        file.write(f"\t@$(ECHO) Compiling Swift module {target.name}\n")
        for out_ref in compile_outputs:
            file.write(f"\t@$(MKDIR) $(dir {out_ref})\n")
        file.write(
            f"\t@$(SWIFTC) $({flags_var}) $({xcc_var}) $({modulesearch_var})"
            f" -o $({obj_var})"
            f" $(addprefix $(WORKSPACE_ROOT)/,$({srcs_var}))\n\n"
        )

    def _write_metal_makefile(self, file: TextIO):
        target = self.target

        if self.config.platform not in METAL_PLATFORM:
            raise ValueError(
                f"metal_library '{target.name}' is not supported on platform "
                f"'{self.config.platform}' (Metal is Apple-only); supported: "
                f"{sorted(METAL_PLATFORM)}"
            )
        sdk, triple = METAL_PLATFORM[self.config.platform]

        air_var = self.var_name("METAL_AIR")
        flags_var = self.var_name("METALFLAGS")

        metal_srcs = [
            Path(os.path.relpath(src, self.workspace.root)).as_posix()
            for src in resolve_conditionals(config=self.config, value=target.srcs)
            if os.path.splitext(src)[-1] in METAL_EXTS
        ]

        user_flags = list(
            resolve_conditionals(config=self.config, value=target.metal_flags)
        )

        file.writelines(["# Generated by Builderer\n", "\n"])
        file.writelines([f"{self.phony}: {self.out_path}\n", "\n"])

        file.write(f"{flags_var} := -target {triple} {' '.join(user_flags)}\n\n")

        # One .air per source, keyed off the workspace-relative source path (the
        # same $(OBJS_ROOT)/%: $(WORKSPACE_ROOT)/% idiom the cc writer uses).
        air_subdir = f"$(OBJS_ROOT)/.metal/{self.package.name}/{target.name}"
        airs = [f"{air_subdir}/{src}.air" for src in metal_srcs]
        file.writelines(
            [
                f"{air_var} :=",
                *[f" \\\n  {air}" for air in airs],
                "\n\n",
            ]
        )

        # Compile rule: .metal -> .air
        for src, air in zip(metal_srcs, airs):
            file.writelines(
                [
                    f"{air}: $(WORKSPACE_ROOT)/{src}\n",
                    f"\t@$(ECHO) Compiling Metal {Path(src).name}\n",
                    f"\t@$(MKDIR) $(dir $@)\n",
                    f"\t@xcrun -sdk {sdk} metal -c $({flags_var}) -o $@ $<\n",
                    "\n",
                ]
            )

        # Link rule: all .air -> the bare <target.name>.metallib file (out_path).
        # The consuming app copies this file to its resources root; whether it
        # becomes the default library (makeDefaultLibrary()) or a URL-loaded
        # library is determined purely by its filename (the target name).
        file.writelines(
            [
                f"{self.out_path}: $({air_var})\n",
                f"\t@$(ECHO) Linking Metal library $@\n",
                f"\t@$(MKDIR) $(dir $@)\n",
                f"\t@xcrun -sdk {sdk} metallib -o $@ $^\n",
                "\n",
            ]
        )

    def _write_apple_application_makefile(self, file: TextIO):
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
        plist_xml_lines = _plist_dict_to_xml_text(info_plist).splitlines()
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
        file.writelines(
            [
                "# Generated by Builderer\n",
                "\n",
                f"{self.phony}: {self.out_path}\n",
                "\n",
                f"{self.out_path}: $(WORKSPACE_ROOT)/{binary_path}",
                *[f" $(WORKSPACE_ROOT)/{src}" for src, _ in resource_pairs],
                *[f" {metallib_path}" for metallib_path, _ in metal_libs],
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
