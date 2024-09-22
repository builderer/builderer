from typing import Union

from builderer.config import Config

# from builderer import Condition, Case, Switch
#
# pkg.cc_library(
#     ...
#     cxx_flags = [
#         Optional(Condition(toolchain="msvc"),          "/std:c++17", "/Zc:__cplusplus"),
#         Optional(Condition(toolchain=["clang","gcc"]), "--std=c++17"),
#         Switch(
#             Case(Condition(toolchain="msvc", build_config="debug"),            "/Od", "/Zi"),
#             Case(Condition(toolchain="msvc", build_config="release"),          "/O2"),
#             Case(Condition(toolchain=["clang","gcc"], build_config="debug"),   "-O0", "-g"),
#             Case(Condition(toolchain=["clang","gcc"], build_config="release"), "-O2"),
#         ),
#     ]
# )


class Condition:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def can_expand(self, config: Config):
        for k, v in self.__dict__.items():
            if k not in config.__dict__:
                continue
            if isinstance(config.__dict__[k], list):
                return False
        return True

    def __call__(self, config: Config):
        for k, v in self.__dict__.items():
            if k not in config.__dict__:
                return False
            if isinstance(config.__dict__[k], list):
                raise ValueError(f"cannot expand list {k}")
            if isinstance(v, list):
                if config.__dict__[k] not in v:
                    return False
            else:
                if config.__dict__[k] != v:
                    return False
        return True


class Case:
    def __init__(self, condition: Condition, *value: str):
        self.condition = condition
        self.values = [*value]


class ConditionalValue:
    def __call__(self, config: Config, permissive: bool = False):
        raise RuntimeError(f"{type(self)} must implement __call__")


class Optional(ConditionalValue):
    def __init__(self, condition: Condition, *value: str):
        self.condition = condition
        self.values = [*value]

    def __call__(self, config: Config, permissive: bool = False):
        if permissive and not self.condition.can_expand(config):
            yield self
        elif self.condition(config):
            for value in self.values:
                yield value


class Switch(ConditionalValue):
    def __init__(self, *cases: Case):
        self.cases: list[Case] = list(cases)

    def __call__(self, config: Config, permissive: bool = False):
        for case in self.cases:
            if permissive and not case.condition.can_expand(config):
                yield self
                return
            if case.condition(config):
                for value in case.values:
                    yield value
                return
        raise RuntimeError("no cases match config")
