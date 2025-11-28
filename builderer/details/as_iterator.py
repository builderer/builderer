from typing import List, Set, Tuple, Union, Iterator


# Provide an iterator over provided strings. Typically used where you dont care if you have a scalar or set of strings.
def str_iter(strings: Union[str, List[str], Set[str], Tuple[str]]) -> Iterator[str]:
    if isinstance(strings, (list, set, tuple)):
        for v in strings:
            assert isinstance(v, str)
            yield v
    else:
        assert isinstance(strings, str)
        yield strings


# The reverse of str_iter. If you know you should have a scalar, use this. Will raise an error if you dont.
def str_scalar(value: Union[str, List[str], Set[str], Tuple[str]]) -> str:
    if isinstance(value, str):
        return value
    elif isinstance(value, (list, set, tuple)) and len(value) == 1:
        return str_scalar(next(iter(value)))
    else:
        raise ValueError(f"expected str or list/set/tuple of length 1, got {value}")
