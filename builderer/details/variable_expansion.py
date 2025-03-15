from copy import deepcopy

from builderer import Config, ConditionalValue
from builderer.details.as_iterator import str_iter


def resolve_conditionals(config: Config, value, permissive: bool = False):
    def visit(inner_value):
        if isinstance(inner_value, ConditionalValue):
            yield from inner_value(config=config, permissive=permissive)
        else:
            yield resolve_conditionals(
                config=config, value=inner_value, permissive=permissive
            )

    if isinstance(value, list):
        return [r for v in value for r in visit(v)]
    elif isinstance(value, ConditionalValue):
        resolved = list(visit(value))
        assert len(resolved) == 1
        return resolved[0]
    else:
        return value


def resolve_variables(config: Config, variables: dict, value):
    if isinstance(value, list):
        return [
            resolve_variables(config=config, variables=variables, value=v)
            for v in value
        ]
    elif isinstance(value, str):
        return value.format_map(variables)
    else:
        return value


def bake_config(config: Config, *, architecture: str, build_config: str) -> Config:
    """
    Create a baked configuration with specified architecture and build configuration.

    Args:
        config: The original configuration to bake.
        architecture: The architecture to set in the baked config.
        build_config: The build configuration to set in the baked config.

    Returns:
        A new Config object with the specified architecture and build configuration.
    """
    assert architecture in str_iter(config.architecture)
    assert build_config in str_iter(config.build_config)
    config = deepcopy(config)
    config.architecture = architecture
    config.build_config = build_config
    return config
