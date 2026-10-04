"""The json5 reader the tests of this repository share: it reads the forms
the exposure documents use, and refuses every other form instead of reading
it wrong."""

from __future__ import annotations

import pytest

from exposure_json5 import Json5Error, parse_json5, strip_comments, unescape


def test_strings_keep_their_comment_markers() -> None:
    assert strip_comments('{ a: "http://x", b: 1 /* c */ } // d') == '{ a: "http://x", b: 1  } '
    assert strip_comments("{ a: 'it\\'s // not a comment' }") == "{ a: 'it\\'s // not a comment' }"


def test_escapes_read_as_the_text_they_name() -> None:
    assert unescape('say \\"hi\\"\\n\\tit\\\'s \\\\ done') == "say \"hi\"\n\tit's \\ done"


def test_the_forms_the_documents_use_are_read() -> None:
    document = """// A comment before the document.
    {
      bare: 1,
      "double": "x // not a comment",
      'single': 'it\\'s',
      /* a block comment */ nested: { list: [true, false, null, -2.5e1, .5, 3.,], empty: {}, none: [] },
      quoted: "say \\"hi\\"",
    }"""
    assert parse_json5(document) == {
        "bare": 1,
        "double": "x // not a comment",
        "single": "it's",
        "nested": {"list": [True, False, None, -25.0, 0.5, 3.0], "empty": {}, "none": []},
        "quoted": 'say "hi"',
    }


def test_an_object_keeps_the_order_of_its_keys() -> None:
    assert list(parse_json5("{ b: 1, a: 2, c: 3 }")) == ["b", "a", "c"]


def test_an_int_stays_an_int() -> None:
    assert parse_json5("[7, -7, +7]") == [7, -7, 7]
    assert all(type(value) is int for value in parse_json5("[7, -7, +7]"))


@pytest.mark.parametrize(
    "document",
    [
        "{ a: 0x10 }",
        "{ a: Infinity }",
        "{ a: NaN }",
        "{ a: 1 } trailing",
        "{ a: 1, a: 2 }",
        '{ a: "\\u0041" }',
        '{ a: "line \\\n continued" }',
        '{ a: "open }',
        "{ a: 'two\nlines' }",
        "{ a 1 }",
        "{ a: 1 b: 2 }",
        "[1 2]",
        "{ 1a: 1 }",
        "",
    ],
)
def test_a_form_the_reader_does_not_read_is_refused(document: str) -> None:
    with pytest.raises(Json5Error):
        parse_json5(document)
