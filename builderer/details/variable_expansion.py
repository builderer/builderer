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

    def resolve_dict_items(items):
        # Recurse into dict VALUES (keys must be plain, never conditional). Each
        # value resolves like a list element but fills a single slot: an empty
        # stream drops the key, one value fills it (more than one is invalid).
        # `permissive` is threaded so values conditioned on list-valued config
        # fields defer in phase 1, like list elements.
        for k, v in items:
            resolved = list(visit(v))
            assert len(resolved) <= 1
            for single in resolved:  # 0 -> key dropped, 1 -> key kept
                yield k, single

    if isinstance(value, list):
        return [r for v in value for r in visit(v)]
    elif isinstance(value, dict):
        return dict(resolve_dict_items(value.items()))
    elif isinstance(value, ConditionalValue):
        # A top-level conditional fills a single slot: 0 values -> the field is
        # absent (None), 1 -> that value. (More than one cannot fit a scalar
        # field.) This mirrors the per-key drop semantics for dict values.
        resolved = list(visit(value))
        assert len(resolved) <= 1
        return resolved[0] if resolved else None
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


# Create a baked configuration with specified architecture and build configuration.
def bake_config(config: Config, *, architecture: str, build_config: str) -> Config:
    assert architecture in str_iter(config.architecture)
    assert build_config in str_iter(config.build_config)
    config = deepcopy(config)
    config.architecture = architecture
    config.build_config = build_config
    return config
