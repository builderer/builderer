from builderer.generators.xcode.model import FileType, generate_id


def test_filetype_from_extension_maps_known_and_falls_back_to_text():
    assert FileType.from_extension(".cpp") == FileType.CPP
    assert FileType.from_extension("mm") == FileType.OBJCPP  # accepts no leading dot
    assert FileType.from_extension(".h") == FileType.C_HEADER
    assert FileType.from_extension(".xyz") == FileType.TEXT  # unknown -> TEXT


def test_generate_id_is_24_chars_and_unique_per_key():
    # Xcode object identifiers must be 24-char and stable per key
    assert len(generate_id("k")) == 24
    assert generate_id("k") != generate_id("other")
