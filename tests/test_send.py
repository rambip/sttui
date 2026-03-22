from sttui.send import format_body


def test_format_body_no_format() -> None:
    parts = ["hello world", "goodbye world"]
    result = format_body(None, parts)
    assert result == "hello world\n\ngoodbye world"


def test_format_body_zero_only() -> None:
    parts = ["hello world", "goodbye world"]
    result = format_body('{"text": "$0"}', parts)
    assert result == '{"text": "hello world\n\ngoodbye world"}'


def test_format_body_positional() -> None:
    parts = ["first part", "second part", "third part"]
    result = format_body("$1 -- $2", parts)
    assert result == "first part -- second part"


def test_format_body_mixed() -> None:
    parts = ["intro", "body"]
    result = format_body('{"first": "$1", "all": "$0"}', parts)
    assert result == '{"first": "intro", "all": "intro\n\nbody"}'


def test_format_body_missing_index() -> None:
    parts = ["only"]
    result = format_body("$1 and $2", parts)
    assert result == "only and $2"


def test_format_body_single_part() -> None:
    parts = ["solo transcript"]
    result = format_body("$0", parts)
    assert result == "solo transcript"


def test_format_body_empty_parts() -> None:
    parts = []
    result = format_body("$0", parts)
    assert result == ""
