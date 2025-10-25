from typing import List, Set, Tuple, Union, Iterator


# Make scalar string or container of straings iteratable...
def str_iter(strings: Union[str, List[str], Set[str], Tuple[str]]) -> Iterator[str]:
    if isinstance(strings, (list, set, tuple)):
        for v in strings:
            assert isinstance(v, str)
            yield v
    else:
        assert isinstance(strings, str)
        yield strings


# Interpret strings or containers of strings as a single string,
# throws exception if there is not exactuly 1 string...
def as_scalar(value: Union[str, List[str], Set[str], Tuple[str]]) -> str:
    if isinstance(value, str):
        return value
    elif isinstance(value, (list, set, tuple)):
        items = list(value)
        if len(items) != 1:
            raise ValueError(f"expected exactly one value, got {len(items)}: {items}")
        return items[0]
    else:
        raise TypeError(f"expected str or collection, got {type(value)}")
