# Build Files

Build files use Python syntax and are named `BUILD.builderer`. They define targets that represent libraries, executables, and external dependencies.

## Packages

Every build file creates a package:

```python
pkg = CTX.add_package("MyLibrary")
```

The package name **must** equal the package directory's path relative to the workspace root, or Builderer raises an error. A top-level `MyLibrary/` directory uses `"MyLibrary"`; a nested package uses the full slash-separated path, e.g. `"MyProject/SubModule"`.

## Common target parameters

Every target accepts:

- `name` (required) — unique within its package.
- `deps` — targets this one depends on (see [Dependency References](#dependency-references)).
- `condition` — a [`Condition`](configuration.md#condition) that gates the whole target; when it doesn't match the active config, the target is excluded from generation entirely.

Build targets (libraries, binaries, apps) additionally accept `output_path` to override Builderer's output location. If omitted, Builderer chooses an internal default that is intentionally **not** API-stable; set `output_path` explicitly when external tooling needs a predictable path.

## C/C++ Targets

### cc_library

Defines a static library:

```python
pkg.cc_library(
    name = "mylib",
    hdrs = ["include/**/*.h"],         # Public headers
    srcs = ["src/**/*.cpp"],           # Implementation files
    public_includes = ["include"],     # Include paths for consumers
    private_includes = ["src"],        # Internal include paths
    public_defines = ["MYLIB_API"],    # Defines for consumers
    private_defines = ["MYLIB_IMPL"],  # Internal defines
    c_flags = ["-std=c11"],
    cxx_flags = ["-std=c++20"],
    deps = [
        ":other_local_target",         # Same package
        "OtherPackage:target",         # Different package
    ],
)
```

**Glob patterns** like `**/*.cpp` match recursively. Use `*.cpp` for single directory.

**Exclusions** can be specified with the `!` prefix:

```python
pkg.cc_library(
    name = "mylib",
    srcs = [
        "src/**/*.cpp",        # Include all .cpp files
        "!src/platform/**",    # Exclude platform directory
        "!src/**/*_test.cpp",  # Exclude test files
    ],
)
```

### cc_binary

Defines an executable:

```python
pkg.cc_binary(
    name = "myapp",
    srcs = ["main.cpp"],
    deps = [":mylib"],
    output_path = "bin/myapp",  # Optional custom output location
)
```

`cc_binary` accepts `srcs`, `c_flags`, `cxx_flags`, `private_includes`, `private_defines`, `deps`, and `output_path`, plus `link_flags` (linker flags — not available on `cc_library`). It has no `hdrs` or `public_*` fields.

### apple_application

Defines a macOS or iOS `.app` bundle from a `cc_binary` or `swift_binary` target.
On macOS, both the Makefile and Xcode generators build it. On iOS, only the
**Xcode** generator is supported (device signing and provisioning do not map onto
plain Makefiles).

```python
pkg.apple_application(
    name = "myapp.app",
    condition = Condition(platform=["macos", "ios"]),
    binary = ":myapp",
    info_plist = {
        "CFBundleIdentifier": "com.example.myapp",
        "CFBundleVersion": "1",
        "CFBundleShortVersionString": "1.0.0",
        # Platform-specific keys via per-key Optional (A8b):
        "LSMinimumSystemVersion": Optional(Condition(platform="macos"), "13.0"),
        "MinimumOSVersion":       Optional(Condition(platform="ios"),   "16.0"),
        "UILaunchScreen":         Optional(Condition(platform="ios"),   {}),
    },
    device_families = [Optional(Condition(platform="ios"), "iphone", "ipad")],
    development_team = Optional(Condition(platform="ios"), "{__env__:DEVELOPMENT_TEAM}"),
    resources = ["Assets/AppIcon.icns"],
)
```

**Fields:**

- `binary` (required) — references a `cc_binary` or `swift_binary`.
- `info_plist` (required) — a dictionary of `Info.plist` keys. The
  deployment-target key (`MinimumOSVersion` on iOS, `LSMinimumSystemVersion` on
  macOS) sets the deployment target. Values may be scalars, lists, nested dicts,
  or [conditionals](configuration.md#conditionals-in-dicts-and-scalar-fields).
- `resources` — copied into the bundle's resources.
- `deps` (optional) — additional targets to embed into the bundle, currently
  [`metal_library`](#metal_library) targets. Each listed library's
  `<target.name>.metallib` is copied into the app's resources root.
- `device_families` (iOS) — list of `"iphone"`/`"ipad"`; defaults to both. Not
  valid on macOS.
- `development_team` (iOS) — Apple team id for signing **device** builds; the
  simulator needs none. Required to generate an iOS app. Keep it uncommitted via
  `"{__env__:DEVELOPMENT_TEAM}"` (see [`.builderer.env`](configuration.md#buildererenv)).
- `output_path` (optional) — the deployable (device) bundle location. If omitted,
  Builderer uses an internal, non-API-stable location.

One iOS config produces a single Xcode project covering both device and
simulator, selected at build time (Xcode destination or `xcodebuild -sdk`) — not
a builderer conditional.

### metal_library

Compiles one or more `.metal` shader files into a Metal library file
(`<target.name>.metallib`), built as a native Xcode
`com.apple.product-type.metal-library` target. It is a discrete, standalone,
shareable target — named like any other library. Declare it in an
[`apple_application`](#apple_application)'s `deps` to embed its
`<target.name>.metallib` at the app's resources root.

How the app loads it follows from the target name:

- a target named `default` → `default.metallib` at the app root, loadable with
  `device.makeDefaultLibrary()`.
- any other name (e.g. `Effects`) → `Effects.metallib` at the app root, loaded by
  URL with `device.makeLibrary(URL:)`.

```python
# Named "default" -> default.metallib, loadable via device.makeDefaultLibrary().
pkg.metal_library(
    name = "default",
    srcs = ["Shaders.metal"],   # one or more .metal files, linked into one library
)
# Any other name -> <name>.metallib, loaded via device.makeLibrary(URL:).
pkg.metal_library(
    name = "Effects",
    srcs = ["Effects.metal"],
)

pkg.apple_application(
    name = "Demo.app",
    binary = ":demo",
    deps = [":default", ":Effects"],  # both .metallib files embedded at the resources root
    info_plist = { ... },
)
```

Load them at runtime:

```swift
// default.metallib
let defaultLib = device.makeDefaultLibrary()
// Effects.metallib
let url = Bundle.main.url(forResource: "Effects", withExtension: "metallib")!
let effects = try device.makeLibrary(URL: url)
```

**Fields:**

- `srcs` — `.metal` source files; all are compiled and linked into a single
  metallib.
- `metal_flags` (optional) — flags passed to the Metal compiler.
- `output_path` (optional) — custom output location.

**Notes:**

- Metal is Apple-only: supported by the `xcode` generator (macOS and iOS) and the
  `make` generator (macOS).
- An app may depend on several `metal_library` targets to ship multiple,
  separately loadable shader libraries — each must have a distinct target name
  (a duplicate `.metallib` filename is rejected at generate time).
- Only `apple_application` targets may depend on a `metal_library`; a single
  `metal_library` may be shared by multiple apps.

## Swift Targets

Builderer supports Swift via three target types. Swift targets interoperate with
C and C++ cleanly in both directions; `cc_library` is not modified to accommodate
Swift — the bridging lives entirely on the Swift side.

### swift_library

Defines a Swift static library:

```python
pkg.swift_library(
    name = "Greeter",
    srcs = ["Greeter/*.swift"],
    swift_flags = ["-target", "arm64-apple-macos13.0"],
    deps = [
        ":CalcBridge",    # swift_cc_module to import C/C++ symbols
        ":OtherSwift",    # other swift_library to import Swift modules
    ],
    cxx_interop = False,  # set True to enable -cxx-interoperability-mode=default
    swift_header = None,  # set to a filename (e.g. "Greeter-Swift.h") to expose
                          # the library to C/C++ consumers; unset = Swift-only
)
```

- `srcs` — `.swift` files. Whole-module compilation: every change to any source
  triggers a full module rebuild.
- `swift_header` — opt-in. When set (e.g. `"Greeter-Swift.h"`), swiftc emits the
  C-callable header at a deterministic build-output location and C/C++ consumers
  can `#include "Greeter-Swift.h"`. When unset (default), no header is emitted
  and the library is Swift-only.
- `cxx_interop` — when `True`, enables `-cxx-interoperability-mode=default` so
  Swift code can `import` C++ modules (templates, classes, `std::string`), and
  the emitted header (if any) is written in C++ dialect rather than Obj-C.
- Module name is always the target `name`. Downstream Swift code does
  `import Greeter`.

### swift_binary

Defines a Swift executable:

```python
pkg.swift_binary(
    name = "calc",
    srcs = ["calc/*.swift"],
    swift_flags = ["-target", "arm64-apple-macos13.0"],
    link_flags = [
        "-target", "arm64-apple-macos13.0",  # also needed at link time
        "-framework", "SwiftUI",
    ],
    deps = [":CalcBridge"],
    cxx_interop = False,
)
```

- `link_flags` is processed by `swiftc` acting as the link driver (so Swift
  runtime and rpaths are handled automatically). `-target` must appear in
  **both** `swift_flags` and `link_flags`; define a shared variable in your
  `RULES.builderer` to keep it DRY.
- When a `cc_binary` transitively depends on a `swift_library`, Builderer
  automatically switches that binary's linker driver from `$(CCLD)` to
  `$(SWIFTC)` so the Swift runtime is linked correctly.

### swift_cc_module

Adapts one or more `cc_library` targets so they can be `import`-ed from Swift:

```python
pkg.swift_cc_module(
    name = "CalcBridge",
    module_maps = ["calc/Lib/CalcBridge.modulemap"],
    deps = [":calc_lib"],
)
```

- `module_maps` — list of hand-authored `.modulemap` files (at least one required). Each file declares
  one or more clang modules whose names become Swift `import` names.
- `deps` — the `cc_library` targets whose public headers the modulemap(s)
  reference.
- This target produces no compiled artifact; it's a metadata target. When a
  `swift_library` or `swift_binary` depends on it, Builderer adds the right
  `-Xcc -fmodule-map-file=…` and `-Xcc -I…` flags to the swiftc invocation,
  and propagates the cc_library's `.a` files as link inputs.

Example modulemap (`calc/Lib/CalcBridge.modulemap`):

```
module CalcBridge {
    header "calc.h"
    export *
}
```

A `cc_library` is never modified to expose itself to Swift — the modulemap and
the `swift_cc_module` are how that decision lives on the Swift side. The same
pattern can be used to bind any other language to C in the future without
polluting `cc_library`.

### Interop matrix

| Direction     | Bridge needed?                                 | User authors                  | Builderer arranges                                                         |
|---------------|------------------------------------------------|-------------------------------|----------------------------------------------------------------------------|
| swift → swift | No                                             | nothing extra                 | `-I` for `.swiftmodule`, link `.a`                                         |
| swift → C/C++ | **`swift_cc_module`**                          | `.modulemap`                  | `-Xcc -fmodule-map-file=…`, `-Xcc -I…`, link cc `.a`                       |
| C/C++ → swift | No — set `swift_header` on the `swift_library` | `@_cdecl`/`public` Swift APIs | `-emit-objc-header-path`, `-I` to consumer, swap linker driver to `swiftc` |

## External Dependencies

### git_repository

Fetches code from Git:

```python
pkg.git_repository(
    name = "FmtRepo",
    remote = "https://github.com/fmtlib/fmt.git",
    sha = "10.2.1",                    # Tag, branch, or commit SHA
)
```

### https_repository

Fetches and extracts an archive from HTTPS:

```python
pkg.https_repository(
    name = "MbedTLSRepo",
    url = "https://github.com/Mbed-TLS/mbedtls/releases/download/mbedtls-4.0.0/mbedtls-4.0.0.tar.bz2",
    sha256 = "2f3a47f7b3a541ddef450e4867eeecb7ce2ef7776093f3a11d6d43ead6bf2827",
)
```

`sha256` must be a 64-character hexadecimal SHA-256 digest.

Reference the repository in paths using `{Package:Target}` expansion:

```python
pkg.cc_library(
    name = "Fmt",
    hdrs = ["{MyPackage:FmtRepo}/include/**/*.h"],
    srcs = ["{MyPackage:FmtRepo}/src/*.cc"],
    public_includes = ["{MyPackage:FmtRepo}/include"],
    deps = [":FmtRepo"],  # Must depend on repo for path expansion
)
```

### generate_files

Generates files during build file generation (not during compilation). The generator command runs when you execute `builderer generate` or `builderer build`, before the native build system is invoked.

```python
pkg.generate_files(
    name = "generated_config",
    args = ["{__python__}", "scripts/generate_config.py", "config.yml"],
    srcs = ["scripts/generate_config.py", "config.yml"],
)
```

`args` is the command line invoked from the package's workspace root. Use the `{__python__}` template variable to invoke the Python interpreter currently running builderer — this resolves to `sys.executable` at run time but keeps the sandbox hash stable across shells/IDEs/CI (whereas hardcoding `sys.executable` would bake an env-specific path into the hash and fragment the sandbox).

`srcs` declares the files whose modification time is folded into the sandbox hash — `touch`ing or editing a script or input data invalidates the sandbox and re-runs the generator, same as `make`. `srcs` supports `{Package:TargetName}` path expansion and glob patterns just like `cc_library.srcs`.

Generated files are placed in the sandbox and can be referenced in other targets using `{Package:TargetName}` path expansion (remember to add it to `deps`).

## Sandboxing

Sandboxing is useful when you need to separate public headers from private implementation files in the include search path. Third-party libraries often mix their public headers with internal implementation headers, tests, examples, and other files you don't want leaking into the public header search paths.

```python
pkg.cc_library(
    name = "external_lib",
    hdrs = ["external/**/*.h"],  # Public headers only
    srcs = ["external/**/*.c"],  # Implementation files
    sandbox = True,              # Separate hdrs and srcs into different paths
    deps = [...],
)
```

When `sandbox=True`, Builderer copies `hdrs` to one sandbox directory and `srcs` to another within `sandbox_root` (defined in your config). This ensures public headers have a clean include path without pollution from implementation details. Relative paths are maintained within each sandbox, so `#include "subdir/header.h"` still works as expected.

Sandboxing also enforces that `hdrs` and `srcs` properly enumerate all required files. Since only explicitly listed files are copied to the sandbox, builds will fail if you've missed a dependency rather than silently succeeding by finding undeclared files.

## Dependency References

- **Local target** (same package): `:target_name`
- **External target**: `PackageName:target_name`
- **Nested package**: `Parent/Child:target_name`

String fields also expand these template variables:

- `{Package:Target}` — path to a sandboxed dependency's files.
- `{__sandbox__}` — path to the target's own sandbox directory (sandboxed targets only); handy in non-path fields such as `generate_files.args`.
- `{__python__}` — the Python interpreter running builderer (`sys.executable`).
- `{__env__:NAME}` — a local value from [`.builderer.env`](configuration.md#buildererenv)
  (e.g. `"{__env__:DEVELOPMENT_TEAM}"`). Works anywhere a string is accepted,
  including embedded in paths.

Example:

```python
pkg = CTX.add_package("App")

pkg.cc_binary(
    name = "app",
    deps = [
        ":utils",              # App:utils
        "Core:foundation",     # Core:foundation
        "External/Libs:json",  # External/Libs:json
    ],
)
```

### Allowed dependency types

Builderer validates every **direct** dependency edge against the consumer's type (the transitive closure is unrestricted) and raises on a disallowed edge:

| Target                                       | May directly depend on                                                                               |
|----------------------------------------------|------------------------------------------------------------------------------------------------------|
| `cc_library`, `cc_binary`, `swift_cc_module` | `cc_library`, `git_repository`, `https_repository`, `generate_files`                                 |
| `swift_library`, `swift_binary`              | `swift_library`, `swift_cc_module`, `git_repository`, `https_repository`, `generate_files`           |
| `apple_application`                          | `cc_binary`, `swift_binary`, `metal_library`, `git_repository`, `https_repository`, `generate_files` |
| `metal_library`, `generate_files`            | `git_repository`, `https_repository`, `generate_files`                                               |

Notably, Swift targets cannot depend on a `cc_library` directly — bridge it through a [`swift_cc_module`](#swift_cc_module).

## Common Patterns

### Header-only libraries

```python
pkg.cc_library(
    name = "header_only",
    hdrs = ["include/**/*.h"],
    public_includes = ["include"],
    # No srcs
)
```

### Platform-specific sources

Use conditionals (see [configuration.md](configuration.md)):

```python
from builderer import Condition, Optional

pkg.cc_library(
    name = "platform",
    srcs = [
        Optional(Condition(platform="windows"), "src/win32/*.cpp"),
        Optional(Condition(platform="linux"),   "src/linux/*.cpp"),
        Optional(Condition(platform="macos"),   "src/macos/*.mm"),
    ],
)
```

### Organizing large projects

Group related targets in subdirectories:

```
Project/
├── BUILD.builderer          # Root package with high-level targets
├── Core/
│   └── BUILD.builderer      # Core:foundation, Core:utils
└── External/
    └── BUILD.builderer      # External:zlib, External:curl
```

