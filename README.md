# 🏗️ Builderer - a fast, dependency-free, build-file generator
[![Actions Status](https://github.com/builderer/builderer/workflows/CI/badge.svg?branch=main)](https://github.com/builderer/builderer/actions)
[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/builderer/builderer/blob/main/LICENSE)
[![GitHub](https://img.shields.io/badge/repo-github-green.svg)](https://github.com/builderer/builderer)

## Status
Builderer is currently a work-in-progress but is capable of generating Visual
Studio and Makefile build files that can target Windows, Linux and macOS.

## Examples
Visit the [example repository](https://github.com/builderer/builderer-examples)
for basic usage instructions and example build files.

## Design Goals
### No system-level dependencies!
 - Builderer can be embedded in a repository, included as a submodule or
   managed with Python venv. This ensures your project always has the right
   version of Builderer at every revision!
 - No system-level dependencies (besides Python and your toolchain of choice)
   need to be installed on developer machines.
### Generating native build files is incredibly fast...
 - Typically less than 1-second for even large projects. Fast enough that
   typical integrations can re-generate projects on every build.
### Generated build files look and feel native
 - Build files don't reference back to or depend on Builderer, they are
   standalone and transferable.
 - This ensures compatability with a wide range of development tools and
   plugins build for the target build system (static analysis, profilers, etc).
 - Configuration branches are evaluated in the build files rather than during
   generation when possible, allowing you to generate once and build many
   configurations from that one set of build files.
### Handle extremely large code bases / mono-repos
 - Beyond being generally fast, you can easily generate build files for only
   portions of the dependency graph you care about.
### Human readable and familiar syntax
 - Its just Python, with an API thats similar to Blaze, Bazel and Buck but
   without the JVM!
### Easy to modify and extend
 - Implemented in a relatively small amount of Python code to make sure its
   approachable to developers.
 - Being just a set of Python scripts without any sort of shared/system
   install required, its easy to modify and extend as needed depending on your
   repositories unique requirements.
### Current focus on C/C++/ObjC development
 - Designed to support the future expansion of toolchains/languages either
   within Builderer itself, or as third party Python modules.
