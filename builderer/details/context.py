from pathlib import Path
from typing import Callable, Dict

from builderer import Config
from builderer.details.package import Package


class Context:
    def __init__(self, root: Path):
        self.root = root


class ConfigContext(Context):
    FILENAME = "CONFIG.builderer"
    MODULENAME = "config"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.buildtools: Dict[str, Callable] = {}
        self.configs: Dict[str, Config] = {}

    def add_buildtool(self, name: str, generator: Callable):
        if name in self.buildtools:
            raise RuntimeError(f"buildtool {name} has already been registered")
        self.buildtools[name] = generator

    def add_config(self, name: str, **kwargs):
        if name in self.configs:
            raise RuntimeError(f"config {name} has already been registered")
        self.configs[name] = Config(**kwargs)


class BuildContext(Context):
    FILENAME = "BUILD.builderer"
    MODULENAME = "build"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.packages: Dict[str, Package] = {}

    def add_package(self, name: str) -> Package:
        if name != self.root.as_posix():
            # TODO: do we care about this? any reason not to let users decouple package name and path?
            raise ValueError(
                f"package name='{name}' does not match root='{self.root.as_posix()}'"
            )
        if name in self.packages:
            raise ValueError(f"package with name='{name}' already exists")
        self.packages[name] = Package(name=name, root=self.root)
        return self.packages[name]


class RulesContext(Context):
    FILENAME = "RULES.builderer"
    MODULENAME = "rules"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rules: Dict[str, Callable] = {}

    def add_rule(self, rule: Callable):
        if rule.__name__ in self.rules:
            raise RuntimeError(f"rules context already contains {rule.__name__}")
        self.rules[rule.__name__] = rule
