# Build Files

Build files use Python syntax and are named `BUILD.builderer`. They define targets that represent libraries, executables, and external dependencies.

## Packages

Every build file creates a package:

```python
pkg = CTX.add_package("MyLibrary")
```

Package names should match the directory path: `"MyProject/SubModule"`

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

Supports all the same parameters as `cc_library` except `hdrs` and `public_*` fields.

`output_path` is optional. If omitted, Builderer chooses an internal default artifact
location that is intentionally **not** API-stable. If you need a stable/predictable path
for external tooling, set `output_path` explicitly.

### apple_application

Defines a macOS `.app` bundle from a `cc_binary` target:

```python
pkg.apple_application(
    name = "myapp_bundle",
    conditional = Condition(platform="macos"),
    binary = ":myapp",
    info_plist = {
        "CFBundleIdentifier": "com.example.myapp",
        "CFBundleVersion": "1",
        "CFBundleShortVersionString": "1.0.0",
    },
    resources = [
        "Assets/AppIcon.icns",
        "Assets/Base.lproj/MainMenu.nib",
    ],
)
```

`binary` is required and must reference a `cc_binary`.  
`resources` are copied into `Contents/Resources` of the app bundle.

`info_plist` is optional and accepts a dictionary with plist-compatible values.
Builderer applies sensible defaults for common keys if omitted.

`output_path` is optional. If omitted, Builderer chooses an internal default artifact
location that is intentionally **not** API-stable. If you need a stable/predictable
bundle location, set `output_path` explicitly.

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

Generates files during build file generation (not during compilation). The generator script runs when you execute `builderer generate` or `builderer build`, before the native build system is invoked.

```python
pkg.generate_files(
    name = "generated_config",
    generator = "scripts/generate_config.py",
    outputs = ["generated/config.h"],
    inputs = ["config.yml"],            # Optional dependencies
)
```

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

