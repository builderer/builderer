# 🏗️ Builderer - a fast, dependency-free, build-file generator
[![CI](https://github.com/builderer/builderer/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/builderer/builderer/actions/workflows/ci.yml)
[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/builderer/builderer/blob/main/LICENSE)
[![GitHub](https://img.shields.io/badge/repo-github-green.svg)](https://github.com/builderer/builderer)

## Documentation

- **[Getting Started](docs/getting-started.md)** - Installation and quick start guide
- **[Build Files](docs/build-files.md)** - Define targets, dependencies, and external libraries
- **[Configuration](docs/configuration.md)** - Configure platforms, toolchains, and conditionals
- **[Commands](docs/commands.md)** - Generate, build, run, and manage projects

## What is Builderer?

Builderer generates native build files from Python-based build descriptions. It's designed for C/C++/Objective-C projects that need to support multiple platforms and toolchains without the complexity of traditional meta-build systems.

### Supported Platforms and Build Systems

| Build System | Windows   | Linux     | macOS     | iOS  | WebAssembly |
|--------------|-----------|-----------|-----------|------|-------------|
| **Makefile** |           | Supported | Supported | TODO | Supported   |
| **MSBuild**  | Supported |           |           |      |             |
| **Xcode**    |           |           | Supported | TODO |             |
| **Ninja**    | TODO      | TODO      | TODO      |      | TODO        |

## Why Builderer?

### Zero System Dependencies
- **Only requires Python 3.9+** - no other system-level dependencies needed
- **No system-wide installation** - use a virtual environment, git submodule, or copy directly into your repository
- **Per-project versioning** - each project can use its own Builderer version without conflicts

### Real Python, Not a DSL
- **Actual Python syntax** - not a Python-like DSL or an old Python fork
- **Familiar to developers** - Python is the world's most popular programming language
- **Simple guardrails** - `CONFIG.builderer`, `RULES.builderer`, and `BUILD.builderer` files provide structure
- **API inspired by Bazel/Buck** - familiar patterns without rigid constraints

### Native Build Files
- **Standalone output** - generated Makefiles and Visual Studio solutions don't depend on Builderer
- **IDE integration** - works seamlessly with Visual Studio and any editor that supports Makefiles
- **Standard tooling support** - static analyzers, profilers, and debuggers work natively
- **Transferable projects** - share generated build files with clients or teammates without Builderer

### Multi-Configuration Support
- **Deferred conditionals** - generate projects that support multiple configurations and architectures
- **Single generation** - produce build files for debug/release, x64/ARM64, etc. in one pass
- **Configuration branches in build files** - switch configurations in your IDE without regenerating

### Fast and Scalable
- **Millisecond generation** - typically under 1 second even for large projects
- **Partial generation** - generate only the targets you need for faster iteration making it mono-repo friendly
- **Smart updates** - only touches files that changed, so IDEs reload seamlessly

### Extensible and Approachable
- **Small, readable codebase** - implemented in straightforward Python
- **Easy to customize** - modify or extend for your project's unique needs
- **No system install needed** - fork and adapt without affecting other projects to meet your custom requirements

### Explicit Yet Concise
- **No magic defaults** - Builderer doesn't make implicit decisions about your build configuration
- **Clear and predictable** - what you write in your build files is exactly what gets generated
- **Still concise** - despite being explicit, target definitions are often just a few lines long
- **Workspace-wide defaults** - use `RULES.builderer` to define common settings once and apply them everywhere
