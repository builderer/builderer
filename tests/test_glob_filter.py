from builderer.details.glob_filter import split_patterns


def test_split_patterns_separates_bang_prefixed_excludes():
    inc, exc = split_patterns(["*.cpp", "!*.test.cpp", "*.h"])
    assert inc == ["*.cpp", "*.h"]
    assert exc == ["*.test.cpp"]  # leading '!' marks an exclude and is stripped


def test_split_patterns_empty():
    assert split_patterns([]) == ([], [])
