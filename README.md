# 🏗️ Builderer - a fast, dependency-free, build-system generator
## Status
Builderer is currently a work-in-progress but is capable of generating Visual
Studio and Makefile build files that can target Windows, Linux and macOS.

## About
- Current focus on C/C++ development
   - Designed to support the future expansion of toolchains/languages either
     within Builderer itself, or as third party Python modules
- No system-level dependencies!
   - Builderer can be embedded in a repository, included as a submodule or
     managed with Python venv. This ensures your project always has the right
     version of Builderer at every revision!
   - No system-level dependencies (besides Python and your toolchain of choice)
     need to be installed on developer machines.
 - Generating native build files is incredibly fast...
   - Typically less than 1-second for even large projects.
 - Generated build files look and feel native
   - Build files don't reference back to Builderer, they are standalone and
     transferable
   - This ensures compatability with a wide range of development tools and
     plugins build for the target build system (static analysis, profilers, etc)
   - Configuration branches are evaluated in the build files rather than during
     generation when possible, allowing you to generate once and build many
     configurations from that one set of build files
 - Handle extremely large code bases / mono-repos
   - Beyond being generally fast, you can easily generate build files for only
     portions of the dependency graph you care about.
 - Human readable and familiar syntax
   - Its just Python, with an API thats similar to Blaze, Bazel and Buck but
     without the JVM!
 - Easy to modify and extend
   - Implemented in a relatively small amount of Python code to make sure its
     approachable to developers
   - Being just a set of Python scripts without any sort of shared/system
     install required, its easy to modify and extend as needed depending on your
     repositories unique requirements

## Quickstart
Python Virtual Environment is a great way of setting up your build environment
with very little boilerplate...
```bash
$ cat requirements.txt
builderer @ git+ssh://git@github.com/builderer/builderer.git@main

$ python -m venv .venv
$ source .venv/bin/activate
$ pip install -r requirements.txt
```


The `CONFIG.builderer` file defines the set of discrete generator settings this
repository supports. Each generator config itself can itself support a large
matrix of build configurations and architectures.
```python
from builderer.generators.msbuild import MsBuildGenerator
from builderer.generators.make import MakeGenerator

CTX.add_buildtool(
    name = "msbuild",
    generator = MsBuildGenerator,
)

CTX.add_buildtool(
    name = "make",
    generator = MakeGenerator,
)

CTX.add_config(
    name = "windows",
    platform = "windows",
    architecture = ["x64", "Win32"],
    buildtool = "msbuild",
    toolchain = "msvc",
    build_config = ["debug", "release"],
    build_root = "build/windows",
    sandbox_root = "build/.sandbox",
)

CTX.add_config(
    name = "linux",
    platform = "linux",
    architecture = ["x86_64", "x86"],
    buildtool = "make",
    toolchain = "gcc",
    build_config = ["debug", "release"],
    build_root = "build/linux",
    sandbox_root = "build/.sandbox",
)
```


The `RULES.builderer` file allows a repository to define custom rules and
aliases to streamline the `BUILD.builderer` files defines later.
```python
from builderer import Optional, Switch, Case, Condition

def cc_binary(ctx, name: str, cxx_flags=[], **kwargs):
    ctx.builtin.cc_binary(
        name = name,
        cxx_flags = [
            Switch(
                Case(Condition(toolchain="msvc"), 
                    "/Zc:__cplusplus",
                    "/std:c++20"),
                Case(Condition(toolchain=["clang","gcc"]), 
                    "-std=c++20")
            ),
            *cxx_flags,
        ],
        output_path = Switch(
            Case(Condition(platform="windows"),
                 f"bin/windows/{name}.exe"),
            Case(Condition(platform="linux"),
                 f"bin/linux/{name}"),
        ),
        **kwargs
    )

CTX.add_rule(cc_binary)
```

`BUILD.builderer` files can then be placed in any directory that has build
targets, each file produces a "Package" that can encapsulate an arbitrary number
of build targets.
```python
pkg = CTX.add_package("MyProject")

pkg.cc_binary(
    name = "HelloWorld",
    srcs = [
      "*.cpp",
      "*.h",
    ],
)
```

Example of building and running...
```bash
$ builderer --config=linux generate
$ make -C .build/linux -j$(nproc) build
$ ./bin/linux/HelloWorld
```