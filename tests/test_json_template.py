import json

import pytest

from perfmon.protocols.json_template import render_json
from perfmon.template import TemplateError


def test_render_json_removes_keys_and_items_that_are_null():
    template = '{"a": {{a}}, "b": "{{b}}", "c": [1, {{a}}, "{{b}}"], "d": {"e": {{a}}, "f": "é"}}'
    assert json.loads(render_json(template, {"a": None, "b": None})) == {"c": [1], "d": {"f": "é"}}
    assert "é" in render_json(template, {"a": None, "b": None})


def test_render_json_leaves_the_text_alone_without_nulls():
    template = '{ "a":   {{a}} }'
    assert render_json(template, {"a": 1}) == '{ "a":   1 }'


@pytest.mark.parametrize("template", ['{"a": "x {{a}}"}', '{"a": "{{a}}{{a}}"}', "{{a}}"])
def test_render_json_rejects_null_inside_a_longer_value(template: str):
    with pytest.raises(TemplateError, match="a is null, which can only leave out a whole JSON value"):
        render_json(template, {"a": None})


@pytest.mark.parametrize("value", ['He said "hi"', "line1\nline2", "C:\\temp\\new", "tab\there", "blåbær ☕"])
def test_render_json_escapes_text_placed_inside_a_string(value: str):
    rendered = render_json('{"title": "{{v}}", "note": "about {{v}}!", "raw": {{n}}}', {"v": value, "n": "5"})
    assert json.loads(rendered) == {"title": value, "note": f"about {value}!", "raw": 5}


def test_render_json_escapes_non_text_values_inside_a_string_too():
    rendered = render_json('{"a": "tags={{tags}}", "b": {{tags}}, "c": "\\"{{n}}\\""}', {"tags": ["x"], "n": 1})
    assert json.loads(rendered) == {"a": 'tags=["x"]', "b": ["x"], "c": '"1"'}
