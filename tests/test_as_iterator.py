import pytest

from builderer.details.as_iterator import str_iter, str_scalar


def test_str_iter_normalizes_scalar_and_collections():
    assert list(str_iter("a")) == ["a"]
    assert list(str_iter(["a", "b"])) == ["a", "b"]
    assert list(str_iter({"a"})) == ["a"]


def test_str_scalar_unwraps_single_value():
    assert str_scalar("a") == "a"
    assert str_scalar(["a"]) == "a"


def test_str_scalar_rejects_ambiguous_input():
    # a scalar is expected, so 0 or >1 elements must fail loudly rather than guess
    with pytest.raises(ValueError):
        str_scalar(["a", "b"])
    with pytest.raises(ValueError):
        str_scalar([])
