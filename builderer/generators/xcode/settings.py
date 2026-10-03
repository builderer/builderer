# Xcode build settings that correspond to compiler, linker and Swift flags.
#
# A flag maps to a setting when Xcode emits exactly that flag for one of the
# setting's values (a fixed value, "<prefix><value>", or "<flag> <value>"); the
# flag is then removed from OTHER_*FLAGS and set as the setting instead. A
# warning flag that matches clang's default maps to the value at which Xcode
# adds nothing. Settings that Builderer or Xcode own (SDK, target triple, module
# name, file lists, ...) and settings whose condition Builderer's projects never
# meet are not mapped; their flags stay on the command line.
#
# Each setting's default is written at project level so Xcode adds no flags of
# its own: the value that emits nothing, or, where every value emits a flag, the
# value matching the compiler's default. Settings Xcode derives from a user or
# scheme toggle (sanitizers, color diagnostics, ...) have no default.

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

from builderer.generators.xcode.model import YesNo

SettingValue = Union[str, YesNo]

YES = YesNo.YES
NO = YesNo.NO


@dataclass(frozen=True)
class XcodeSetting:
    name: str  # Xcode build setting name
    default: Optional[SettingValue]  # Project-level value, None to leave Xcode's
    choices: Dict[str, SettingValue] = field(
        default_factory=dict
    )  # flag -> value mapping


@dataclass(frozen=True)
class FlagTable:
    settings: List[XcodeSetting]
    # "<prefix><value>" flags: prefix -> (setting, whether values accumulate)
    attached: Dict[str, Tuple[str, bool]]
    # "<flag> <value>" flags: flag -> (setting, whether values accumulate)
    next_arg: Dict[str, Tuple[str, bool]]


def parse(
    table: FlagTable, flags: List[str]
) -> Tuple[Dict[str, Union[SettingValue, List[str]]], List[str]]:
    fixed = {f: (s.name, v) for s in table.settings for f, v in s.choices.items()}
    settings: Dict[str, Union[SettingValue, List[str]]] = {}
    remaining: List[str] = []
    i = 0
    while i < len(flags):
        flag = flags[i]
        i += 1
        if flag in fixed:
            name, value = fixed[flag]
            settings[name] = value
            continue
        entry: Optional[Tuple[str, bool]] = None
        if flag in table.next_arg and i < len(flags):
            entry, user_value = table.next_arg[flag], flags[i]
            i += 1
        else:
            for prefix, candidate in table.attached.items():
                if flag.startswith(prefix) and len(flag) > len(prefix):
                    entry, user_value = candidate, flag[len(prefix) :]
                    break
        if entry is None:
            remaining.append(flag)
            continue
        name, is_list = entry
        if is_list:
            values = settings.setdefault(name, [])
            assert isinstance(values, list)
            values.append(user_value)
        else:
            settings[name] = user_value
    return settings, remaining


CLANG_FLAGS = FlagTable(
    settings=[
        XcodeSetting(
            "print_note_include_stack",
            NO,
            {"-fdiagnostics-show-note-include-stack": YES},
        ),
        XcodeSetting(
            "CLANG_RETAIN_COMMENTS_FROM_SYSTEM_HEADERS",
            NO,
            {"-fretain-comments-from-system-headers": YES},
        ),
        XcodeSetting(
            "CLANG_COLOR_DIAGNOSTICS",
            None,
            {"-fcolor-diagnostics": YES, "-fno-color-diagnostics": NO},
        ),
        XcodeSetting("GCC_USE_STANDARD_INCLUDE_SEARCHING", YES, {"-nostdinc": NO}),
        XcodeSetting(
            "GCC_C_LANGUAGE_STANDARD",
            "compiler-default",
            {
                "-ansi": "ansi",
                "-std=c89": "c89",
                "-std=gnu89": "gnu89",
                "-std=c99": "c99",
                "-std=gnu99": "gnu99",
                "-std=c11": "c11",
                "-std=gnu11": "gnu11",
                "-std=c17": "c17",
                "-std=gnu17": "gnu17",
                "-std=c23": "c23",
                "-std=gnu23": "gnu23",
                "-std=c90": "c89",
                "-std=gnu90": "gnu89",
                "-std=c1x": "c11",
                "-std=gnu1x": "gnu11",
                "-std=c18": "c17",
                "-std=gnu18": "gnu17",
                "-std=c2x": "c23",
                "-std=gnu2x": "gnu23",
            },
        ),
        XcodeSetting(
            "CLANG_CXX_LANGUAGE_STANDARD",
            "compiler-default",
            {
                "-std=c++98": "c++98",
                "-std=gnu++98": "gnu++98",
                "-std=c++11": "c++0x",
                "-std=gnu++11": "gnu++0x",
                "-std=c++14": "c++14",
                "-std=gnu++14": "gnu++14",
                "-std=c++17": "c++17",
                "-std=gnu++17": "gnu++17",
                "-std=c++20": "c++20",
                "-std=gnu++20": "gnu++20",
                "-std=c++23": "c++23",
                "-std=gnu++23": "gnu++23",
                "-std=c++0x": "c++0x",
                "-std=gnu++0x": "gnu++0x",
                "-std=c++1y": "c++14",
                "-std=gnu++1y": "gnu++14",
                "-std=c++1z": "c++17",
                "-std=gnu++1z": "gnu++17",
                "-std=c++2a": "c++20",
                "-std=gnu++2a": "gnu++20",
                "-std=c++2b": "c++23",
                "-std=gnu++2b": "gnu++23",
                "-std=c++26": "c++26",
                "-std=gnu++26": "gnu++26",
                "-std=c++2c": "c++26",
                "-std=gnu++2c": "gnu++26",
            },
        ),
        XcodeSetting(
            "CLANG_CXX_LIBRARY", "compiler-default", {"-stdlib=libc++": "libc++"}
        ),
        XcodeSetting("CLANG_ENABLE_OBJC_ARC", NO, {"-fobjc-arc": YES}),
        XcodeSetting("CLANG_ENABLE_OBJC_WEAK", NO, {"-fobjc-weak": YES}),
        XcodeSetting("CLANG_ENABLE_MODULES", NO, {"-fmodules": YES}),
        XcodeSetting("CLANG_DISABLE_CXX_MODULES", NO, {"-fno-cxx-modules": YES}),
        XcodeSetting("CLANG_DEBUG_MODULES", None, {"-gmodules": YES}),
        XcodeSetting("CLANG_MODULES_AUTOLINK", YES, {"-fno-autolink": NO}),
        XcodeSetting(
            "CLANG_MODULES_VALIDATE_SYSTEM_HEADERS",
            NO,
            {"-fmodules-validate-system-headers": YES},
        ),
        XcodeSetting(
            "CLANG_ENABLE_BOUNDS_ATTRIBUTES", NO, {"-fbounds-attributes": YES}
        ),
        XcodeSetting("CLANG_ENABLE_BOUNDS_SAFETY", None, {"-fbounds-safety": YES}),
        XcodeSetting(
            "CLANG_BOUNDS_SAFETY_BRINGUP_MISSING_CHECKS",
            "default",
            {
                "-fno-bounds-safety-bringup-missing-checks": "none",
            },
        ),
        XcodeSetting(
            "CLANG_ENABLE_APP_EXTENSION", None, {"-fapplication-extension": YES}
        ),
        XcodeSetting("GCC_CHAR_IS_UNSIGNED_CHAR", NO, {"-funsigned-char": YES}),
        XcodeSetting("GCC_ENABLE_ASM_KEYWORD", YES, {"-fno-asm": NO}),
        XcodeSetting("GCC_ENABLE_BUILTIN_FUNCTIONS", YES, {"-fno-builtin": NO}),
        XcodeSetting(
            "GCC_ENABLE_TRIGRAPHS", NO, {"-trigraphs": YES, "-Wno-trigraphs": NO}
        ),
        XcodeSetting("GCC_ENABLE_CPP_EXCEPTIONS", YES, {"-fno-exceptions": NO}),
        XcodeSetting(
            "CLANG_CXX_STANDARD_LIBRARY_HARDENING",
            "",
            {
                "-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_NONE": "none",
                "-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST": "fast",
                "-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_EXTENSIVE": "extensive",
                "-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG": "debug",
            },
        ),
        XcodeSetting("GCC_ENABLE_PASCAL_STRINGS", NO, {"-fpascal-strings": YES}),
        XcodeSetting("GCC_SHORT_ENUMS", NO, {"-fshort-enums": YES}),
        XcodeSetting("GCC_LINK_WITH_DYNAMIC_LIBRARIES", YES, {"-static": NO}),
        XcodeSetting(
            "GCC_ENABLE_FLOATING_POINT_LIBRARY_CALLS", NO, {"-msoft-float": YES}
        ),
        XcodeSetting(
            "CLANG_ENABLE_CPP_STATIC_DESTRUCTORS",
            YES,
            {"-fno-c++-static-destructors": NO},
        ),
        XcodeSetting(
            "CLANG_WARN_UNSAFE_BUFFER_USAGE",
            "DEFAULT",
            {
                "-Wunsafe-buffer-usage": YES,
                "-Werror=unsafe-buffer-usage": "YES_ERROR",
                "-Wno-unsafe-buffer-usage": NO,
            },
        ),
        XcodeSetting(
            "GCC_OPTIMIZATION_LEVEL",
            "0",
            {
                "-O0": "0",
                "-O1": "1",
                "-O2": "2",
                "-O3": "3",
                "-Os": "s",
                "-Ofast": "fast",
                "-Oz": "z",
            },
        ),
        XcodeSetting("LLVM_LTO", NO, {"-flto": YES, "-flto=thin": "YES_THIN"}),
        XcodeSetting("GCC_NO_COMMON_BLOCKS", NO, {"-fno-common": YES}),
        XcodeSetting("GCC_REUSE_STRINGS", YES, {"-fwritable-strings": NO}),
        XcodeSetting("GCC_DYNAMIC_NO_PIC", NO, {"-mdynamic-no-pic": YES}),
        XcodeSetting("GCC_ENABLE_KERNEL_DEVELOPMENT", NO, {"-mkernel": YES}),
        XcodeSetting(
            "GCC_TREAT_WARNINGS_AS_ERRORS", NO, {"-Werror": YES, "-Wno-error": NO}
        ),
        XcodeSetting(
            "GCC_TREAT_IMPLICIT_FUNCTION_DECLARATIONS_AS_ERRORS",
            NO,
            {
                "-Werror=implicit-function-declaration": YES,
            },
        ),
        XcodeSetting(
            "GCC_TREAT_INCOMPATIBLE_POINTER_TYPE_WARNINGS_AS_ERRORS",
            NO,
            {
                "-Werror=incompatible-pointer-types": YES,
            },
        ),
        XcodeSetting(
            "GCC_WARN_ABOUT_MISSING_FIELD_INITIALIZERS",
            NO,
            {
                "-Wmissing-field-initializers": YES,
                "-Wno-missing-field-initializers": NO,
            },
        ),
        XcodeSetting(
            "GCC_WARN_ABOUT_MISSING_PROTOTYPES",
            NO,
            {"-Wmissing-prototypes": YES, "-Wno-missing-prototypes": NO},
        ),
        XcodeSetting(
            "GCC_WARN_ABOUT_RETURN_TYPE",
            YES,
            {
                "-Wno-return-type": NO,
                "-Werror=return-type": "YES_ERROR",
                "-Wreturn-type": YES,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_DOCUMENTATION_COMMENTS",
            NO,
            {"-Wdocumentation": YES, "-Wno-documentation": NO},
        ),
        XcodeSetting(
            "CLANG_WARN_UNREACHABLE_CODE",
            NO,
            {
                "-Wunreachable-code": YES,
                "-Wunreachable-code-aggressive": "YES_AGGRESSIVE",
                "-Wno-unreachable-code": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_QUOTED_INCLUDE_IN_FRAMEWORK_HEADER",
            NO,
            {
                "-Wquoted-include-in-framework-header": YES,
                "-Wno-quoted-include-in-framework-header": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_FRAMEWORK_INCLUDE_PRIVATE_FROM_PUBLIC",
            NO,
            {
                "-Wframework-include-private-from-public": YES,
                "-Wno-framework-include-private-from-public": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_NULLABLE_TO_NONNULL_CONVERSION",
            NO,
            {
                "-Wnullable-to-nonnull-conversion": YES,
                "-Wno-nullable-to-nonnull-conversion": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_OBJC_IMPLICIT_ATOMIC_PROPERTIES",
            NO,
            {
                "-Wimplicit-atomic-properties": YES,
                "-Wno-implicit-atomic-properties": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_DIRECT_OBJC_ISA_USAGE",
            YES,
            {
                "-Wno-deprecated-objc-isa-usage": NO,
                "-Werror=deprecated-objc-isa-usage": "YES_ERROR",
                "-Wdeprecated-objc-isa-usage": YES,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_OBJC_INTERFACE_IVARS",
            "",
            {
                "-Wno-objc-interface-ivars": NO,
                "-Wobjc-interface-ivars": YES,
                "-Werror=objc-interface-ivars": "YES_ERROR",
            },
        ),
        XcodeSetting(
            "CLANG_WARN_OBJC_MISSING_PROPERTY_SYNTHESIS",
            NO,
            {
                "-Wobjc-missing-property-synthesis": YES,
                "-Wno-objc-missing-property-synthesis": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_OBJC_ROOT_CLASS",
            YES,
            {
                "-Wno-objc-root-class": NO,
                "-Werror=objc-root-class": "YES_ERROR",
                "-Wobjc-root-class": YES,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_OBJC_REPEATED_USE_OF_WEAK",
            "",
            {"-Wno-arc-repeated-use-of-weak": NO},
        ),
        XcodeSetting(
            "CLANG_WARN_OBJC_EXPLICIT_OWNERSHIP_TYPE",
            NO,
            {
                "-Wexplicit-ownership-type": YES,
                "-Wno-explicit-ownership-type": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_OBJC_IMPLICIT_RETAIN_SELF",
            NO,
            {
                "-Wimplicit-retain-self": YES,
                "-Wno-implicit-retain-self": NO,
            },
        ),
        XcodeSetting(
            "GCC_WARN_NON_VIRTUAL_DESTRUCTOR",
            NO,
            {"-Wnon-virtual-dtor": YES, "-Wno-non-virtual-dtor": NO},
        ),
        XcodeSetting(
            "GCC_WARN_HIDDEN_VIRTUAL_FUNCTIONS",
            NO,
            {"-Woverloaded-virtual": YES, "-Wno-overloaded-virtual": NO},
        ),
        XcodeSetting(
            "CLANG_WARN__EXIT_TIME_DESTRUCTORS",
            NO,
            {
                "-Wexit-time-destructors": YES,
                "-Wno-exit-time-destructors": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN__ARC_BRIDGE_CAST_NONARC",
            YES,
            {
                "-Wno-arc-bridge-casts-disallowed-in-nonarc": NO,
                "-Warc-bridge-casts-disallowed-in-nonarc": YES,
            },
        ),
        XcodeSetting(
            "CLANG_WARN__DUPLICATE_METHOD_MATCH",
            NO,
            {
                "-Wduplicate-method-match": YES,
                "-Wno-duplicate-method-match": NO,
            },
        ),
        XcodeSetting(
            "GCC_WARN_TYPECHECK_CALLS_TO_PRINTF",
            YES,
            {"-Wno-format": NO, "-Wformat": YES},
        ),
        XcodeSetting(
            "GCC_WARN_INITIALIZER_NOT_FULLY_BRACKETED",
            NO,
            {"-Wmissing-braces": YES, "-Wno-missing-braces": NO},
        ),
        XcodeSetting(
            "GCC_WARN_MISSING_PARENTHESES",
            NO,
            {"-Wparentheses": YES, "-Wno-parentheses": NO},
        ),
        XcodeSetting(
            "GCC_WARN_CHECK_SWITCH_STATEMENTS",
            YES,
            {"-Wswitch": YES, "-Wno-switch": NO},
        ),
        XcodeSetting(
            "CLANG_WARN_COMPLETION_HANDLER_MISUSE",
            NO,
            {
                "-Wcompletion-handler": YES,
                "-Wno-completion-handler": NO,
            },
        ),
        XcodeSetting(
            "GCC_WARN_UNUSED_FUNCTION",
            NO,
            {"-Wunused-function": YES, "-Wno-unused-function": NO},
        ),
        XcodeSetting(
            "GCC_WARN_UNUSED_LABEL",
            NO,
            {"-Wunused-label": YES, "-Wno-unused-label": NO},
        ),
        XcodeSetting(
            "CLANG_WARN_EMPTY_BODY", YES, {"-Wempty-body": YES, "-Wno-empty-body": NO}
        ),
        XcodeSetting(
            "GCC_WARN_UNINITIALIZED_AUTOS",
            "",
            {"-Wuninitialized": YES, "-Wno-uninitialized": NO},
        ),
        XcodeSetting(
            "GCC_WARN_UNKNOWN_PRAGMAS",
            NO,
            {"-Wunknown-pragmas": YES, "-Wno-unknown-pragmas": NO},
        ),
        XcodeSetting("GCC_WARN_INHIBIT_ALL_WARNINGS", None, {"-w": YES}),
        XcodeSetting(
            "GCC_WARN_PEDANTIC",
            NO,
            {"-pedantic": YES, "-Wpedantic": YES, "-Wno-pedantic": NO},
        ),
        XcodeSetting("GCC_WARN_SHADOW", NO, {"-Wshadow": YES, "-Wno-shadow": NO}),
        XcodeSetting(
            "GCC_WARN_FOUR_CHARACTER_CONSTANTS",
            NO,
            {
                "-Wfour-char-constants": YES,
                "-Wno-four-char-constants": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_SUSPICIOUS_IMPLICIT_CONVERSION",
            "",
            {
                "-Wconversion": YES,
                "-Werror=conversion": "YES_ERROR",
                "-Wno-conversion": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_CONSTANT_CONVERSION",
            "",
            {
                "-Wconstant-conversion": YES,
                "-Werror=constant-conversion": "YES_ERROR",
                "-Wno-constant-conversion": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_INT_CONVERSION",
            "",
            {
                "-Wint-conversion": YES,
                "-Werror=int-conversion": "YES_ERROR",
                "-Wno-int-conversion": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_BOOL_CONVERSION",
            "",
            {
                "-Wbool-conversion": YES,
                "-Werror=bool-conversion": "YES_ERROR",
                "-Wno-bool-conversion": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_ENUM_CONVERSION",
            "",
            {
                "-Wenum-conversion": YES,
                "-Werror=enum-conversion": "YES_ERROR",
                "-Wno-enum-conversion": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_FLOAT_CONVERSION",
            "",
            {
                "-Wfloat-conversion": YES,
                "-Werror=float-conversion": "YES_ERROR",
                "-Wno-float-conversion": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_NON_LITERAL_NULL_CONVERSION",
            "",
            {
                "-Wnon-literal-null-conversion": YES,
                "-Werror=non-literal-null-conversion": "YES_ERROR",
                "-Wno-non-literal-null-conversion": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_OBJC_LITERAL_CONVERSION",
            "",
            {
                "-Wobjc-literal-conversion": YES,
                "-Werror=objc-literal-conversion": "YES_ERROR",
                "-Wno-objc-literal-conversion": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_MISSING_NOESCAPE",
            YES,
            {
                "-Werror=missing-noescape": "YES_ERROR",
                "-Wno-missing-noescape": NO,
                "-Wmissing-noescape": YES,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_PRAGMA_PACK",
            YES,
            {
                "-Werror=pragma-pack": "YES_ERROR",
                "-Wno-pragma-pack": NO,
                "-Wpragma-pack": YES,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_PRIVATE_MODULE",
            YES,
            {"-Wno-private-module": NO, "-Wprivate-module": YES},
        ),
        XcodeSetting(
            "CLANG_WARN_VEXING_PARSE",
            YES,
            {
                "-Werror=vexing-parse": "YES_ERROR",
                "-Wno-vexing-parse": NO,
                "-Wvexing-parse": YES,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_DELETE_NON_VIRTUAL_DTOR",
            YES,
            {
                "-Werror=delete-non-virtual-dtor": "YES_ERROR",
                "-Wno-delete-non-virtual-dtor": NO,
                "-Wdelete-non-virtual-dtor": YES,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_ASSIGN_ENUM", NO, {"-Wassign-enum": YES, "-Wno-assign-enum": NO}
        ),
        XcodeSetting(
            "GCC_WARN_SIGN_COMPARE",
            NO,
            {"-Wsign-compare": YES, "-Wno-sign-compare": NO},
        ),
        XcodeSetting(
            "GCC_WARN_MULTIPLE_DEFINITION_TYPES_FOR_SELECTOR",
            NO,
            {"-Wselector": YES, "-Wno-selector": NO},
        ),
        XcodeSetting(
            "GCC_WARN_STRICT_SELECTOR_MATCH",
            NO,
            {
                "-Wstrict-selector-match": YES,
                "-Wno-strict-selector-match": NO,
            },
        ),
        XcodeSetting(
            "GCC_WARN_UNDECLARED_SELECTOR",
            NO,
            {"-Wundeclared-selector": YES, "-Wno-undeclared-selector": NO},
        ),
        XcodeSetting(
            "CLANG_WARN_DEPRECATED_OBJC_IMPLEMENTATIONS",
            NO,
            {
                "-Wdeprecated-implementations": YES,
                "-Wno-deprecated-implementations": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_CXX0X_EXTENSIONS",
            NO,
            {"-Wc++11-extensions": YES, "-Wno-c++11-extensions": NO},
        ),
        XcodeSetting(
            "CLANG_WARN_ATOMIC_IMPLICIT_SEQ_CST",
            NO,
            {
                "-Watomic-implicit-seq-cst": YES,
                "-Wno-atomic-implicit-seq-cst": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_IMPLICIT_FALLTHROUGH",
            "",
            {
                "-Wimplicit-fallthrough": YES,
                "-Wno-implicit-fallthrough": NO,
                "-Werror=implicit-fallthrough": "YES_ERROR",
            },
        ),
        XcodeSetting(
            "CLANG_TRIVIAL_AUTO_VAR_INIT",
            "default",
            {
                "-ftrivial-auto-var-init=uninitialized": "uninitialized",
                "-ftrivial-auto-var-init=zero": "zero",
                "-ftrivial-auto-var-init=pattern": "pattern",
            },
        ),
        XcodeSetting("ENABLE_NS_ASSERTIONS", YES, {"-DNS_BLOCK_ASSERTIONS=1": NO}),
        XcodeSetting(
            "ENABLE_STRICT_OBJC_MSGSEND",
            YES,
            {
                "-DOBJC_OLD_DISPATCH_PROTOTYPES=0": YES,
                "-DOBJC_OLD_DISPATCH_PROTOTYPES=1": NO,
            },
        ),
        XcodeSetting("ENABLE_APPLE_KEXT_CODE_GENERATION", NO, {"-fapple-kext": YES}),
        XcodeSetting(
            "GCC_WARN_UNUSED_PARAMETER",
            NO,
            {"-Wunused-parameter": YES, "-Wno-unused-parameter": NO},
        ),
        XcodeSetting(
            "GCC_WARN_UNUSED_VARIABLE",
            NO,
            {"-Wunused-variable": YES, "-Wno-unused-variable": NO},
        ),
        XcodeSetting(
            "GCC_WARN_UNUSED_VALUE",
            YES,
            {"-Wunused-value": YES, "-Wno-unused-value": NO},
        ),
        XcodeSetting(
            "CLANG_WARN_XNU_TYPED_ALLOCATORS",
            "DEFAULT",
            {
                "-Wxnu-typed-allocators": YES,
                "-Werror=xnu-typed-allocators": "YES_ERROR",
                "-Wno-xnu-typed-allocators": NO,
            },
        ),
        XcodeSetting("GCC_ENABLE_EXCEPTIONS", NO, {"-fexceptions": YES}),
        XcodeSetting("GCC_ENABLE_OBJC_EXCEPTIONS", YES, {"-fno-objc-exceptions": NO}),
        XcodeSetting(
            "CLANG_ENABLE_OBJC_ARC_EXCEPTIONS", NO, {"-fobjc-arc-exceptions": YES}
        ),
        XcodeSetting("GCC_CW_ASM_SYNTAX", NO, {"-fasm-blocks": YES}),
        XcodeSetting("GCC_UNROLL_LOOPS", NO, {"-funroll-loops": YES}),
        XcodeSetting("GCC_FAST_MATH", NO, {"-ffast-math": YES}),
        XcodeSetting(
            "GCC_STRICT_ALIASING",
            YES,
            {"-fstrict-aliasing": YES, "-fno-strict-aliasing": NO},
        ),
        XcodeSetting("GCC_INSTRUMENT_PROGRAM_FLOW_ARCS", NO, {"-fprofile-arcs": YES}),
        XcodeSetting("GCC_GENERATE_TEST_COVERAGE_FILES", NO, {"-ftest-coverage": YES}),
        XcodeSetting(
            "GCC_WARN_ALLOW_INCOMPLETE_PROTOCOL",
            YES,
            {"-Wprotocol": YES, "-Wno-protocol": NO},
        ),
        XcodeSetting(
            "GCC_WARN_ABOUT_DEPRECATED_FUNCTIONS",
            YES,
            {
                "-Wdeprecated-declarations": YES,
                "-Wno-deprecated-declarations": NO,
            },
        ),
        XcodeSetting(
            "GCC_WARN_ABOUT_INVALID_OFFSETOF_MACRO",
            YES,
            {
                "-Winvalid-offsetof": YES,
                "-Wno-invalid-offsetof": NO,
            },
        ),
        XcodeSetting(
            "GCC_DEBUG_INFORMATION_VERSION",
            None,
            {"-gdwarf-4": "dwarf4", "-gdwarf-5": "dwarf5"},
        ),
        XcodeSetting(
            "CLANG_DEBUG_INFORMATION_LEVEL",
            "default",
            {"-gline-tables-only": "line-tables-only"},
        ),
        XcodeSetting(
            "CLANG_X86_VECTOR_INSTRUCTIONS",
            "default",
            {
                "-msse3": "sse3",
                "-mssse3": "ssse3",
                "-msse4.1": "sse4.1",
                "-msse4.2": "sse4.2",
                "-mavx": "avx",
                "-mavx2": "avx2",
                "-march=skylake-avx512": "avx512",
            },
        ),
        XcodeSetting("GCC_SYMBOLS_PRIVATE_EXTERN", NO, {"-fvisibility=hidden": YES}),
        XcodeSetting(
            "GCC_INLINES_ARE_PRIVATE_EXTERN", NO, {"-fvisibility-inlines-hidden": YES}
        ),
        XcodeSetting("GCC_THREADSAFE_STATICS", YES, {"-fno-threadsafe-statics": NO}),
        XcodeSetting(
            "GCC_WARN_ABOUT_POINTER_SIGNEDNESS",
            YES,
            {"-Wpointer-sign": YES, "-Wno-pointer-sign": NO},
        ),
        XcodeSetting(
            "GCC_WARN_ABOUT_MISSING_NEWLINE",
            NO,
            {"-Wnewline-eof": YES, "-Wno-newline-eof": NO},
        ),
        XcodeSetting(
            "CLANG_WARN_IMPLICIT_SIGN_CONVERSION",
            "",
            {
                "-Wsign-conversion": YES,
                "-Werror=sign-conversion": "YES_ERROR",
                "-Wno-sign-conversion": NO,
            },
        ),
        XcodeSetting(
            "GCC_WARN_64_TO_32_BIT_CONVERSION",
            "",
            {
                "-Wshorten-64-to-32": YES,
                "-Werror=shorten-64-to-32": "YES_ERROR",
                "-Wno-shorten-64-to-32": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_INFINITE_RECURSION",
            NO,
            {"-Winfinite-recursion": YES, "-Wno-infinite-recursion": NO},
        ),
        XcodeSetting(
            "CLANG_WARN_SUSPICIOUS_MOVE", NO, {"-Wmove": YES, "-Wno-move": NO}
        ),
        XcodeSetting(
            "CLANG_WARN_COMMA",
            "",
            {"-Wcomma": YES, "-Wno-comma": NO, "-Werror=comma": "YES_ERROR"},
        ),
        XcodeSetting(
            "CLANG_WARN_BLOCK_CAPTURE_AUTORELEASING",
            "",
            {
                "-Wblock-capture-autoreleasing": YES,
                "-Wno-block-capture-autoreleasing": NO,
                "-Werror=block-capture-autoreleasing": "YES_ERROR",
            },
        ),
        XcodeSetting(
            "CLANG_WARN_STRICT_PROTOTYPES",
            "",
            {
                "-Wstrict-prototypes": YES,
                "-Wno-strict-prototypes": NO,
                "-Werror=strict-prototypes": "YES_ERROR",
            },
        ),
        XcodeSetting(
            "CLANG_WARN_RANGE_LOOP_ANALYSIS",
            NO,
            {"-Wrange-loop-analysis": YES, "-Wno-range-loop-analysis": NO},
        ),
        XcodeSetting(
            "CLANG_WARN_SEMICOLON_BEFORE_METHOD_BODY",
            NO,
            {
                "-Wsemicolon-before-method-body": YES,
                "-Wno-semicolon-before-method-body": NO,
            },
        ),
        XcodeSetting(
            "CLANG_WARN_UNGUARDED_AVAILABILITY",
            YES,
            {
                "-Wunguarded-availability": YES,
                "-Wno-unguarded-availability": NO,
            },
        ),
        XcodeSetting(
            "GCC_OBJC_ABI_VERSION",
            "",
            {"-fobjc-abi-version=1": "1", "-fobjc-abi-version=2": "2"},
        ),
        XcodeSetting("GCC_OBJC_LEGACY_DISPATCH", NO, {"-fobjc-legacy-dispatch": YES}),
        XcodeSetting(
            "CLANG_INSTRUMENT_FOR_OPTIMIZATION_PROFILING",
            NO,
            {"-fprofile-instr-generate": YES},
        ),
        XcodeSetting("CLANG_SCUDO_SANITIZER", None, {"-fsanitize=scudo": YES}),
        XcodeSetting("CLANG_ADDRESS_SANITIZER", None, {"-fsanitize=address": YES}),
        XcodeSetting(
            "CLANG_ADDRESS_SANITIZER_CONTAINER_OVERFLOW",
            YES,
            {"-D__SANITIZER_DISABLE_CONTAINER_OVERFLOW__": NO},
        ),
        XcodeSetting(
            "CLANG_ADDRESS_SANITIZER_USE_AFTER_SCOPE",
            NO,
            {"-fsanitize-address-use-after-scope": YES},
        ),
        XcodeSetting(
            "CLANG_ADDRESS_SANITIZER_ALLOW_ERROR_RECOVERY",
            None,
            {"-fsanitize-recover=address": YES},
        ),
        XcodeSetting("ENABLE_SYSTEM_SANITIZERS", None, {"-fsanitize-stable-abi": YES}),
        XcodeSetting(
            "CLANG_ENABLE_C_TYPED_ALLOCATOR_SUPPORT",
            "compiler-default",
            {
                "-ftyped-memory-operations": YES,
                "-fno-typed-memory-operations": NO,
            },
        ),
        XcodeSetting(
            "CLANG_OMIT_FRAME_POINTERS",
            "compiler-default",
            {
                "-fomit-frame-pointer": YES,
                "-fno-omit-frame-pointer": NO,
            },
        ),
        XcodeSetting("CLANG_THREAD_SANITIZER", None, {"-fsanitize=thread": YES}),
        XcodeSetting("GCC_GENERATE_DEBUGGING_SYMBOLS", NO, {"-g": YES, "-g0": NO}),
    ],
    attached={
        "-fmessage-length=": ("diagnostic_message_length", False),
        "-fmacro-backtrace-limit=": ("CLANG_MACRO_BACKTRACE_LIMIT", False),
        "-fmodules-prune-interval=": ("CLANG_MODULES_PRUNE_INTERVAL", False),
        "-fmodules-prune-after=": ("CLANG_MODULES_PRUNE_AFTER", False),
        "-fmodules-ignore-macro=": ("CLANG_MODULES_IGNORE_MACROS", True),
        "-fno-bounds-safety-bringup-missing-checks=": (
            "CLANG_BOUNDS_SAFETY_BRINGUP_MISSING_CHECKS_OPT_OUTS",
            False,
        ),
        "-D": ("GCC_PREPROCESSOR_DEFINITIONS", True),
        "-I": ("HEADER_SEARCH_PATHS", True),
        "-F": ("FRAMEWORK_SEARCH_PATHS", True),
        "-mmacosx-version-min=": ("MACOSX_DEPLOYMENT_TARGET", False),
        "-miphoneos-version-min=": ("IPHONEOS_DEPLOYMENT_TARGET", False),
    },
    next_arg={
        "-I": ("HEADER_SEARCH_PATHS", True),
        "-F": ("FRAMEWORK_SEARCH_PATHS", True),
        "-D": ("GCC_PREPROCESSOR_DEFINITIONS", True),
        "-isystem": ("SYSTEM_HEADER_SEARCH_PATHS", True),
        "-iquote": ("USER_HEADER_SEARCH_PATHS", True),
        "-iframework": ("SYSTEM_FRAMEWORK_SEARCH_PATHS", True),
    },
)

LINKER_FLAGS = FlagTable(
    settings=[
        XcodeSetting("CLANG_LD_SUPPRESS_WARNINGS", None, {"-w": YES}),
        XcodeSetting("CLANG_LINK_WITH_STANDARD_LIBRARIES", None, {"-nostdlib": NO}),
        XcodeSetting("KEEP_PRIVATE_EXTERNS", NO, {"-keep_private_externs": YES}),
        XcodeSetting("CLANG_LD_EXPORT_GLOBAL_SYMBOLS", None, {"-rdynamic": YES}),
        XcodeSetting("CLANG_LD_THREAD_SANITIZER", None, {"-fsanitize=thread": YES}),
        XcodeSetting("CLANG_LD_SCUDO_SANITIZER", None, {"-fsanitize=scudo": YES}),
    ],
    attached={
        "-L": ("LIBRARY_SEARCH_PATHS", True),
        "-fuse-ld=": ("CLANG_ALTERNATE_LINKER", False),
        "--ld-path=": ("CLANG_ALTERNATE_LINKER_PATH", False),
    },
    next_arg={
        "-iframework": ("CLANG_SYSTEM_FRAMEWORK_SEARCH_PATHS", True),
        "-init": ("INIT_ROUTINE", False),
        "-exported_symbols_list": ("EXPORTED_SYMBOLS_FILE", False),
        "-unexported_symbols_list": ("UNEXPORTED_SYMBOLS_FILE", False),
        "-bundle_loader": ("BUNDLE_LOADER", False),
        "-e": ("LD_ENTRY_POINT_clang", False),
    },
)

SWIFT_FLAGS = FlagTable(
    settings=[
        XcodeSetting("SWIFT_LIBRARIES_ONLY", NO, {"-parse-as-library": YES}),
        XcodeSetting(
            "SWIFT_CROSS_MODULE_OPTIMIZATION", NO, {"-cross-module-optimization": YES}
        ),
        XcodeSetting(
            "SWIFT_PRECOMPILE_BRIDGING_HEADER", YES, {"-disable-bridging-pch": NO}
        ),
        XcodeSetting(
            "SWIFT_OPTIMIZATION_LEVEL",
            "-Onone",
            {"-Onone": "-Onone", "-O": "-O", "-Osize": "-Osize"},
        ),
        XcodeSetting(
            "SWIFT_LTO", NO, {"-lto=llvm-full": YES, "-lto=llvm-thin": "YES_THIN"}
        ),
        XcodeSetting(
            "SWIFT_COMPILATION_MODE",
            "singlefile",
            {"-whole-module-optimization": "wholemodule"},
        ),
        XcodeSetting(
            "SWIFT_DISABLE_SAFETY_CHECKS", NO, {"-remove-runtime-asserts": YES}
        ),
        XcodeSetting(
            "SWIFT_ENFORCE_EXCLUSIVE_ACCESS",
            "default",
            {
                "-enforce-exclusivity=checked": "on",
                "-enforce-exclusivity=unchecked": "off",
            },
        ),
        XcodeSetting(
            "SWIFT_STRICT_CONCURRENCY",
            "minimal",
            {"-strict-concurrency=targeted": "targeted"},
        ),
        XcodeSetting(
            "SWIFT_DEFAULT_ACTOR_ISOLATION",
            "nonisolated",
            {"-default-isolation=MainActor": "MainActor"},
        ),
        XcodeSetting(
            "SWIFT_STRICT_MEMORY_SAFETY",
            NO,
            {
                "-strict-memory-safety": YES,
                "-strict-memory-safety:migrate": "MIGRATE",
            },
        ),
        XcodeSetting(
            "SWIFT_ENABLE_BARE_SLASH_REGEX", NO, {"-enable-bare-slash-regex": YES}
        ),
        XcodeSetting(
            "SWIFT_ENABLE_APP_EXTENSION", None, {"-application-extension": YES}
        ),
        XcodeSetting("SWIFTC_DISABLE_SANDBOX", NO, {"-disable-sandbox": YES}),
        XcodeSetting("SWIFT_SCUDO_SANITIZER", None, {"-sanitize=scudo": YES}),
        XcodeSetting("SWIFT_ADDRESS_SANITIZER", None, {"-sanitize=address": YES}),
        XcodeSetting(
            "SWIFT_ADDRESS_SANITIZER_ALLOW_ERROR_RECOVERY",
            None,
            {"-sanitize-recover=address": YES},
        ),
        XcodeSetting("SWIFT_THREAD_SANITIZER", None, {"-sanitize=thread": YES}),
        XcodeSetting(
            "SWIFT_MEMORY_TAGGING_ADDRESS_SANITIZER",
            None,
            {"-sanitize=memtag-stack": YES},
        ),
        XcodeSetting("ENABLE_SYSTEM_SANITIZERS", None, {"-sanitize-stable-abi": YES}),
        XcodeSetting("SWIFT_ENABLE_TESTABILITY", NO, {"-enable-testing": YES}),
        XcodeSetting("SWIFT_SUPPRESS_WARNINGS", None, {"-suppress-warnings": YES}),
        XcodeSetting(
            "SWIFT_TREAT_WARNINGS_AS_ERRORS", NO, {"-warnings-as-errors": YES}
        ),
        XcodeSetting(
            "SWIFT_ENABLE_LIBRARY_EVOLUTION", None, {"-enable-library-evolution": YES}
        ),
    ],
    attached={
        "-D": ("SWIFT_ACTIVE_COMPILATION_CONDITIONS", True),
    },
    next_arg={
        "-module-alias": ("SWIFT_MODULE_ALIASES", True),
        "-Wwarning": ("SWIFT_WARNINGS_AS_WARNINGS_GROUPS", True),
        "-Werror": ("SWIFT_WARNINGS_AS_ERRORS_GROUPS", True),
    },
)


def project_settings() -> Dict[str, SettingValue]:
    return {
        s.name: s.default
        for table in (CLANG_FLAGS, LINKER_FLAGS, SWIFT_FLAGS)
        for s in table.settings
        if s.default is not None
    }
