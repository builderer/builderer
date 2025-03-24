# Implementing a New Generator in Builderer

This guide explains how to implement a new build system generator for Builderer. A generator transforms targets defined in a workspace into build system files.

## Generator Responsibility

A generator is responsible for:

1. Accessing and processing workspace targets and their dependencies
2. Expanding variable configurations to produce build variants
3. Identifying relevant source files for each target
4. Extracting compiler/linker flags, include paths, and defines
5. Writing build system files to the correct output locations

## Basic Generator Structure

Each generator should be implemented in its own directory under `builderer/generators/`:

```
builderer/generators/
  └── mygenerator/
      ├── __init__.py   # Main generator class
      └── utils.py      # Helper functions
```

## Generator Implementation

Your generator should implement a main class that:
1. Takes a `Config` object and `Workspace` object
2. Validates supported platforms/toolchains
3. Provides a `__call__` method that processes the workspace and generates build files

### Basic Generator Skeleton

Here's a basic skeleton for implementing a generator:

```python
from builderer import Config
from builderer.details.workspace import Workspace
from pathlib import Path

class MyGenerator:
    def __init__(self, config: Config, workspace: Workspace):
        self.base_config = config
        self.workspace = workspace
        
        # Output root for generated files
        self.output_root = Path(config.build_root)
        
        # Validate configuration
        supported_platforms = ["linux", "macos", "windows"]
        if self.base_config.platform not in supported_platforms:
            raise ValueError(f"Platform {self.base_config.platform} not supported")
    
    def __call__(self):
        # Create output directory
        self.output_root.mkdir(parents=True, exist_ok=True)
        
        # Generate build configurations
        build_configs = self._generate_configs()
        
        # Generate one target file per configuration
        for config in build_configs:
            self._generate_targets_for_config(config)
    
    def _generate_configs(self):
        # Generate all build configurations
        # ...
    
    def _generate_targets_for_config(self, config):
        # Process each target for a specific configuration
        # ...
    
    def _process_target(self, config, package, target):
        # Process a single target
        # ...
```

For a simple example, see the JSON generator implementation in the `builderer/generators/json` directory.

## Accessing Workspace Data

The `Workspace` object provides comprehensive access to the build graph:

### Targets

```python
from builderer.details.targets.target import BuildTarget

# Iterate through all targets in the workspace
for package, target in workspace.targets:
    # Filter for buildable targets only
    if isinstance(target, BuildTarget):
        # Process buildable target
        print(f"Buildable target: {package.name}:{target.name}")
```

### Dependencies

```python
# Get direct dependencies for a target
direct_deps = workspace.direct_dependencies(package, target)

# Get all (recursive) dependencies for a target
all_deps = workspace.all_dependencies(package, target)
```

## Variable Expansion and Build Configurations

Builderer handles configuration options in two different ways:

1. **Generation-time options**: Variables like `architecture` and `build_config` defined in CONFIG.builderer are expanded during generation to create multiple build file variants
2. **Build-time options**: Other options can remain selectable by the end-user at build time

When a developer defines a CONFIG.builderer with multiple options:

```python
# CONFIG.builderer
config = Config(
    architecture=["x64", "arm64"],     # Multiple architectures
    build_config=["debug", "release"], # Multiple build configs
    with_tests=True                    # Single option
)
```

The generator expands the multi-valued options to produce separate build files:

```python
from builderer.details.variable_expansion import bake_config
from builderer.details.as_iterator import str_iter

# Create a separate config object for each architecture + build_config combination
configs = [
    bake_config(base_config, architecture=arch, build_config=build_cfg)
    for arch in str_iter(base_config.architecture)
    for build_cfg in str_iter(base_config.build_config)
]

# This creates 4 distinct build configurations:
# - x64-debug
# - x64-release
# - arm64-debug
# - arm64-release
```

How these configurations are represented in the final build system is entirely up to the generator:

- Some build systems might use separate files for each configuration
- Others might represent options as selectable properties within the same build files
- The mapping from Builderer's configuration matrix to the output format is determined by each generator's implementation

When possible, generators should preserve the multi-dimensional nature of these configurations. If the target build system supports independent selection of architecture and build configuration, flattening these into a one-dimensional list of options would reduce flexibility for end users.

For each configuration, the generator produces a separate set of build files where conditionals have been resolved:

```python
# A target defined with conditional flags:
cc_library(
    name = "example",
    srcs = ["common.cpp"],
    cxx_flags = [
        Optional(Condition(build_config="debug"), "-O0", "-g"),
    ],
)
```

```python
# During generation, these conditionals get resolved for each configuration:
resolved_flags = resolve_conditionals(config=config, value=target.cxx_flags)

# When processing the "debug" config, this becomes ["-O0", "-g"]
```

The end user then selects which configuration's build files to use, rather than having build files with embedded conditionals. This approach makes the build system simpler and more efficient, as conditional evaluation happens once during generation, not on every build.

## Processing Target Data

Extract and process target properties using the type system:

```python
from builderer.details.targets.target import BuildTarget
from builderer.details.targets.cpp_library import CppLibrary
from builderer.details.targets.cpp_binary import CppBinary

# Process source files (common to all BuildTarget subtypes)
source_files = resolve_conditionals(config=config, value=target.srcs)
includes = []
defines = []

# Process private includes/defines
if isinstance(target, (CppLibrary, CppBinary)):
    includes = resolve_conditionals(config=config, value=target.private_includes)
    defines = resolve_conditionals(config=config, value=target.private_defines)
    
# Library targets also have public includes/defines
if isinstance(target, CppLibrary):
    includes.extend(resolve_conditionals(config=config, value=target.public_includes))
    defines.extend(resolve_conditionals(config=config, value=target.public_defines))

# Add dependency includes/defines from library dependencies
dep_includes = [
    inc
    for dep_pkg, dep_target in all_deps 
    if isinstance(dep_target, CppLibrary)
    for inc in resolve_conditionals(config=config, value=dep_target.public_includes)
]
dep_defines = [
    define
    for dep_pkg, dep_target in all_deps 
    if isinstance(dep_target, CppLibrary)
    for define in resolve_conditionals(config=config, value=dep_target.public_defines)
]
includes.extend(dep_includes)
defines.extend(dep_defines)
```

## Best Practices

1. Generate build files that reflect the structure of the workspace
2. Support all relevant build configurations (debug/release, platforms, architectures)
3. Process dependencies correctly for proper build ordering
4. Validate that your generator supports the requested configuration
5. Generate descriptive error messages when requirements aren't met
6. Use consistent output directory structures
