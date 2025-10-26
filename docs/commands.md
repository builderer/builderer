# Commands

Builderer provides several commands for working with your project. All commands require `--config` to specify which configuration to use.

## Common Options

All commands accept:

```bash
--config=<name>  # Required: configuration from CONFIG.builderer
[targets...]     # Optional: specific targets to operate on
```

If no targets are specified, all targets in the workspace are processed.

## generate

Generate native build files (Makefiles, Visual Studio solutions, etc.).

```bash
builderer generate --config=linux
builderer generate --config=windows Tools/MyTool:myapp
```

**When to use**: Run this whenever you modify `*.builderer` files or add/remove source files.

Generated files are placed in the `build_root` specified in your config. They're standalone and don't depend on Builderer to build and can be transferred.

## build

Generate build files (if needed) and compile specified targets.

```bash
builderer build --config=linux
builderer build --config=linux MyApp:app
builderer build --config=windows --build_config=release --build_arch=x64
```

**Optional flags**:
- `--build_config=<config>` — Build a specific configuration (e.g., debug, release)
- `--build_arch=<arch>` — Build a specific architecture (e.g., x86-64, arm64)

This is a convenience that combines `generate` + invoking the native build tool with parallel builds enabled.

## run

Build and execute a binary target.

```bash
builderer run --config=linux Tools:myapp
builderer run --config=linux Tools:myapp -- --app-arg
```

**Arguments after `--`** are passed to the binary.

**Example**:
```bash
builderer run --config=linux Game:shooter -- --fullscreen --level=5
```

## graph

Visualize or export the dependency graph. Outputs the dependency graph in DOT format to stdout. Useful for understanding target relationships.

**Visualize with graphviz**:
```bash
builderer graph --config=linux | dot -Tpng > graph.png
builderer graph --config=linux | xdot -
```

## sources

Display source files and lines of code statistics for targets.

```bash
builderer sources --config=linux
builderer sources --config=linux Core:foundation
```

Outputs a hierarchical breakdown showing:
- Lines of code per package
- Lines of code per target
- Lines of code per attribute (hdrs, srcs)
- Individual file paths with line counts
- Total lines of code across all targets

Useful for understanding codebase size and composition.

## licenses

**Experimental**: Searches for and display licenses from repository dependencies.

```bash
builderer licenses --config=linux
```

Scans `git_repository` targets and attempts to extract license information.

## Target Specification

Targets are specified as `Package:Target`:

```bash
# Single target
builderer build --config=linux Core:foundation

# Multiple targets
builderer build --config=linux Core:foundation Tools:viewer

# All targets in workspace (no target specified)
builderer build --config=linux
```

## Configuration Selection

The `--config` flag selects a configuration defined in `CONFIG.builderer`:

```bash
builderer build --config=linux      # Use linux config
builderer build --config=windows    # Use windows config
builderer build --config=macos      # Use macos config
```

Each config can have:
- Different platforms
- Different toolchains
- Different architectures
- Different output directories

## Working with Configurations

### Multi-architecture builds

If your config defines multiple architectures:

```python
CTX.add_config(
    name = "linux",
    architecture = ["x86-64", "arm64"],
    # ...
)
```

Builderer generates projects for all architectures simultaneously. The native build system (Make/MSBuild) handles building each one.

### Multi-config builds

Similarly for build configurations:

```python
CTX.add_config(
    name = "windows",
    build_config = ["debug", "release", "profile"],
    # ...
)
```

Visual Studio solutions will include all three configurations. Makefiles support building specific configurations using optional `CONFIG` and `ARCH` variables (e.g., `make CONFIG=debug ARCH=x86-64`).

## Integration Examples

### CI/CD

```bash
# Generate and build everything
builderer build --config=linux

# Run tests
builderer run --config=linux Tests:unit_tests -- --verbose
```

### IDE Integration

```bash
# Generate project files for development
builderer generate --config=windows
```

Generation is fast (milliseconds) and only touches files that have changed, so regenerating when nothing has changed is essentially a no-op. You can safely regenerate frequently. Once generated, open the projects in your IDE (e.g., Visual Studio for `.sln` files, or import Makefiles into your editor). Most IDEs will automatically reload when they detect project file changes. Within the IDE, you can select build configuration and architecture from the native UI, then compile, debug, and work with the project like any other native project.
