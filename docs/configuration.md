# Configuration & Conditionals

## CONFIG.builderer

The config file defines build configurations for different platforms and toolchains.

### Basic Configuration

```python
from builderer.generators.make import MakeGenerator
from builderer.generators.msbuild import MsBuildGenerator

# Define build tool generators
CTX.add_buildtool(
    name = "make",
    generator = MakeGenerator,
)

CTX.add_buildtool(
    name = "msbuild",
    generator = MsBuildGenerator,  # Currently defaults to Visual Studio 2022
    # Or specify a version explicitly:
    # generator = MsBuildGenerator[2022],  # Visual Studio 2022
    # generator = MsBuildGenerator[2026],  # Visual Studio 2026 (including Insider releases)
)

# Define a configuration
CTX.add_config(
    name = "linux",
    platform = "linux",                   # windows, linux, macos, ios, emscripten
    architecture = ["x86-64", "arm64"],   # Can be list or single value
    buildtool = "make",
    toolchain = "gcc",                    # gcc, clang, msvc, emscripten
    build_config = ["debug", "release"],  # Can be list or single value
    build_root = "build/linux",
    sandbox_root = "build/.sandbox",      # For git_repository and sandboxed targets
)
```

### iOS

An `ios` config (`buildtool = "xcode"`) produces a **single** Xcode project that
covers both physical devices and the simulator. Choose between them at build time
via the Xcode destination dropdown or `xcodebuild -sdk` — there is no separate
simulator config and no regeneration when switching. Device and simulator
products and intermediates are kept in separate directories so switching never
invalidates the other's build. See [`apple_application`](build-files.md#apple_application)
for signing (`development_team`) and device family, and
[`run`](commands.md#run) for on-device launch.

### Visual Studio Version Selection

When using `MsBuildGenerator`, you can specify which version of Visual Studio to target:

```python
from builderer.generators.msbuild import MsBuildGenerator

# Default: Visual Studio 2022
CTX.add_buildtool(
    name = "msbuild",
    generator = MsBuildGenerator,
)

# Explicitly specify Visual Studio 2022
CTX.add_buildtool(
    name = "msbuild",
    generator = MsBuildGenerator[2022],
)

# Specify Visual Studio 2026 (including Insider releases)
CTX.add_buildtool(
    name = "msbuild",
    generator = MsBuildGenerator[2026],
)
```

**Note**: The build system will automatically locate the correct Visual Studio installation using `vswhere`, including prerelease/Insider versions when using `MsBuildGenerator[2026]`.

### Custom Configuration Fields

Add arbitrary fields for use in conditionals:

```python
CTX.add_config(
    name = "linux",
    platform = "linux",
    # ... standard fields ...
    allocator = "mimalloc",  # Custom field
    profiler = "tracy",      # Custom field
    tls_lib = "openssl",     # Custom field
)
```

## .builderer.env

Optional, gitignored file at the workspace root holding **local, uncommitted
values** that build files reference as `{__env__:NAME}`. It is the place for
machine- or developer-specific values that must not be committed — most commonly
an Apple signing team.

```ini
# .builderer.env  (add to .gitignore)
DEVELOPMENT_TEAM=ABCDE12345
```

Flat `KEY=VALUE` lines; `#` comments and blank lines are ignored. It is plain
text, **not** executed Python.

Reference a value anywhere a string is accepted, including inside paths:

```python
development_team = "{__env__:DEVELOPMENT_TEAM}"
srcs = ["generated/{__env__:VARIANT}/api.cpp"]
```

`{__env__:NAME}` resolves through the same expansion as `{Package:Target}` and
`{__python__}`. The file is the **only** source — the process environment is not
consulted. A referenced name that is not defined fails immediately with a clear
error naming it. Targets excluded from a build (e.g. an iOS-only app on a Windows
build) never resolve their references, so unset values only matter for targets
that are actually built.

## RULES.builderer

Optional file that defines default compile flags and custom rule wrappers.

Builderer has builtin rules (`cc_library`, `cc_binary`, `git_repository`, `https_repository`, etc.), but they must be exposed in `RULES.builderer` to be usable in `BUILD.builderer` files. You can expose them as-is or wrap them to add workspace-wide defaults. This provides concise, readable customization across your entire project.

### Example Rules File

```python
from builderer import Optional, Switch, Case, Condition

# Define reusable flag sets
CXX_FLAGS = Switch(
    Case(Condition(toolchain="msvc"),
        "/std:c++20", "/Zc:__cplusplus", "/EHsc"),
    Case(Condition(toolchain=["clang", "gcc"]),
        "-std=c++20"),
)

CONFIG_FLAGS = Switch(
    Case(Condition(build_config="debug"),
        "-O0", "-g"),
    Case(Condition(build_config="release"),
        "-O2"),
)

# Wrap builtin rules with defaults
def cc_library(ctx, cxx_flags=[], **kwargs):
    ctx.builtin.cc_library(
        cxx_flags = [
            *cxx_flags,      # User-provided flags come first
            CXX_FLAGS,       # Then workspace defaults
            CONFIG_FLAGS,
        ],
        **kwargs             # All other parameters pass through unchanged
    )

CTX.add_rule(cc_library)
```

**Note**: This wrapper intercepts `cxx_flags` to inject workspace defaults while preserving user-provided flags. All other parameters (`hdrs`, `srcs`, `deps`, etc.) pass through via `**kwargs` unchanged.

Now `pkg.cc_library()` automatically includes these flags.

### Exposing Builtin Rules

Make builtin rules visible without modification:

```python
def git_repository(ctx, **kwargs):
    ctx.builtin.git_repository(**kwargs)

CTX.add_rule(git_repository)

def https_repository(ctx, **kwargs):
    ctx.builtin.https_repository(**kwargs)

CTX.add_rule(https_repository)
```

## Conditionals

Builderer provides conditional expressions that evaluate based on config fields.

### Deferred vs Immediate Evaluation

Builderer's conditional system is designed for **deferred evaluation**. Conditionals (`Optional`, `Switch`, `Case`) are evaluated during build file generation, not when parsing `BUILD.builderer` files.
- Build files are analyzed once
- Multiple configurations can be generated from a single analysis
- A config with `architecture = ["x86-64", "arm64"]` generates projects for both architectures

You can still use **Python if-statements** for immediate decisions based on function parameters or logic that doesn't depend on config variations:

```python
# Example: Custom rule wrapper in RULES.builderer
def cc_binary(ctx, name: str, console_app: bool, **kwargs):
    # Immediate evaluation (Python if-statement) - based on parameter
    subsystem_flag = "/SUBSYSTEM:CONSOLE" if console_app else "/SUBSYSTEM:WINDOWS"
    
    ctx.builtin.cc_binary(
        name = name,
        link_flags = [
            # Deferred evaluation (Builderer conditionals) - based on config
            Switch(
                Case(Condition(platform="windows"), subsystem_flag, "user32.lib"),
                Case(Condition(platform="linux"), "-lpthread"),
            ),
        ],
        **kwargs
    )
```

Use Python if-statements when deciding based on parameters or immediate context. Use Builderer conditionals when the decision depends on configuration fields that may have multiple values or vary across build configurations.

### Condition

Matches config fields:

```python
from builderer import Condition

# Match single value
Condition(platform="windows")

# Match any value in list
Condition(toolchain=["gcc", "clang"])

# Match multiple fields (AND logic)
Condition(platform="linux", build_config="debug")

# Match any config (always true)
Condition()
```

### Optional

Include values only when condition matches:

```python
from builderer import Optional, Condition

pkg.cc_library(
    name = "mylib",
    srcs = [
        "common.cpp",
        Optional(Condition(platform="windows"),
            "windows.cpp"),
        Optional(Condition(platform=["linux", "macos"]),
            "posix.cpp"),
    ],
    c_flags = [
        Optional(Condition(build_config="debug"),
            "-DDEBUG", "-g"),
    ],
)
```

### Switch / Case

Select exactly one matching case (first match wins):

```python
from builderer import Switch, Case, Condition

pkg.cc_library(
    name = "mylib",
    srcs = [
        Switch(
            Case(Condition(platform="windows"),  "src/win32/*.cpp"),
            Case(Condition(platform="linux"),    "src/linux/*.cpp"),
            Case(Condition(platform="macos"),    "src/macos/*.mm"),
            Case(Condition(),                    []),  # Default/fallback
        ),
    ],
    link_flags = [
        Switch(
            Case(Condition(platform="windows"),         "user32.lib", "gdi32.lib"),
            Case(Condition(platform=["linux","macos"]), "-lpthread"),
        ),
    ],
)
```

### Conditionals in dicts and scalar fields

`Optional`/`Switch` work in any field, not just lists:

- **Dict values** — a key whose value resolves to nothing is dropped; one that
  resolves to a value is kept. Dict **keys** must be plain strings.
- **Scalar fields** — a field may be set to a single `Optional`/`Switch`; an
  `Optional` that doesn't match leaves the field unset.

```python
pkg.apple_application(
    name = "myapp.app",
    # Scalar field set to a conditional (unset when not iOS):
    development_team = Optional(Condition(platform="ios"), "{__env__:TEAM}"),
    info_plist = {
        "CFBundleName": "MyApp",                                      # always
        "LSMinimumSystemVersion": Optional(Condition(platform="macos"), "13.0"),
        "MinimumOSVersion":       Optional(Condition(platform="ios"),   "16.0"),
    },
)
```

### Conditional Targets

Entire targets can be conditional:

```python
pkg.git_repository(
    name = "TracyRepo",
    condition = Condition(profiler="tracy"),     # Only fetch if enabled
    remote = "https://github.com/wolfpld/tracy.git",
    sha = "v0.10.0",
)

pkg.cc_library(
    name = "Tracy",
    condition = Condition(profiler="tracy"),     # Only build if enabled
    hdrs = ["{MyPackage:TracyRepo}/public/**/*.h"],
    deps = [":TracyRepo"],
)
```
