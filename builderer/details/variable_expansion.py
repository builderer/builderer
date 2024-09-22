from builderer import Config, ConditionalValue


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
