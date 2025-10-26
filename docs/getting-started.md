# Getting Started

## Installation

Builderer requires Python 3.9+ and has no external dependencies.

### Option 1: Virtual environment (recommended)

Create a `requirements.txt` in your repository:
```
git+https://github.com/builderer/builderer.git@<tag-or-commit-sha>
```

Then install in a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

This ensures your project has an isolated, version-controlled Builderer installation without requiring system-wide installation.

### Option 2: Git submodule
```bash
git submodule add https://github.com/builderer/builderer.git
```

Alternatively, embed Builderer directly in your repository to guarantee the exact version at every revision.

## Quick Start

### 1. Create Your First Config

Create `CONFIG.builderer` at your repository root:

```python
from builderer.generators.make import MakeGenerator

# Register a build file generator (Makefiles in this case)
CTX.add_buildtool(
    name = "make",
    generator = MakeGenerator,
)

# Define a build configuration (you can add multiple for different platforms)
CTX.add_config(
    name = "linux",                      # Name to reference this config
    platform = "linux",                  # Target platform
    architecture = ["x86-64"],           # Target architecture(s)
    buildtool = "make",                  # Which generator to use
    toolchain = "gcc",                   # Compiler toolchain
    build_config = ["debug", "release"], # Build configurations to generate
    build_root = "build/linux",          # Where to generate build files
)
```

### 2. Create Your First Build File

Create a directory for your package and add `BUILD.builderer` inside it:

```
MyApp/
└── BUILD.builderer
```

In `MyApp/BUILD.builderer`:

```python
# Package name must match the directory path relative to workspace root
pkg = CTX.add_package("MyApp")

# Define a library target
pkg.cc_library(
    name = "utils",
    hdrs = ["include/*.h"],         # Public headers (glob patterns supported)
    srcs = ["src/*.cpp"],           # Source files
    public_includes = ["include"],  # Include directories for consumers
)

# Define an executable target
pkg.cc_binary(
    name = "myapp",
    srcs = ["main.cpp"],
    deps = [":utils"],              # ":name" references targets in same package
)
```

### 3. Build and Run

```bash
# Build, and run the binary in one command
builderer run --config=linux MyApp:myapp
```

This will:
1. Generate native build files (Makefiles)
2. Compile the target and its dependencies
3. Execute the binary

You can also build without running:

```bash
builderer build --config=linux MyApp:myapp # builds 1 target and its dependencies
builderer build --config=linux             # builds everything in the workspace
```

## Project Structure

A typical Builderer project looks like:

```
MyProject/
├── CONFIG.builderer     # Platform configurations
├── RULES.builderer      # (Optional) Custom rules and defaults
├── MyLib/
│   └── BUILD.builderer  # Package "MyLib" with library targets
├── Tools/
│   └── BUILD.builderer  # Package "Tools" with tool targets
└── External/
    └── BUILD.builderer  # Package "External" for dependencies
```

## Key Concepts

- **CONFIG.builderer**: Defines build configurations (platforms, toolchains, generators)
- **RULES.builderer**: Optional file for custom rules and shared compile flags
- **BUILD.builderer**: Defines build targets in Python (must be in a package directory)
- **Packages**: Directory containing a BUILD.builderer file; name matches directory path
- **Targets**: Individual build units (libraries, binaries, etc.)
- **Dependencies**: Expressed as `"Package:Target"` or `":LocalTarget"` (same package)

## Next Steps

- Learn about [build file structure](build-files.md)
- Understand [configuration and conditionals](configuration.md)
- Explore [available commands](commands.md)

