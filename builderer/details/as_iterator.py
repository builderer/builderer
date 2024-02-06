from typing import List, Set, Tuple, Union, Iterator

# Iterate through provided strings. Useful for makin
def str_iter(strings: Union[str,List[str],Set[str],Tuple[str]]) -> Iterator[str]:
    if isinstance(strings, (list,set,tuple)):
        for v in strings:
            assert isinstance(v, str)
            yield v
    else:
        assert isinstance(strings, str)
        yield strings
