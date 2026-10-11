import pytest

from perfmon.template import TemplateError, placeholders, render, render_mapping, render_optional


def test_substitutes_names_and_dotted_paths():
    context = {"id": 7, "user": {"name": "ada", "tags": ["a", "b"]}}
    assert render("/u/{{id}}/{{ user.name }}/{{user.tags.1}}", context) == "/u/7/ada/b"


def test_non_strings_are_written_as_json_and_nothing_is_escaped():
    body = render('{"ok": {{flag}}, "l": {{items}}, "s": "{{text}}"}', {"flag": True, "items": ["a"], "text": "<a&b>"})
    assert body == '{"ok": true, "l": ["a"], "s": "<a&b>"}'


def test_missing_names_are_all_reported():
    with pytest.raises(TemplateError, match="no value for: a, b.c"):
        render("{{a}} {{b.c}} {{a}}", {"b": {}})


def test_builtins():
    first, second = render("{{$uuid}}", {}), render("{{$uuid}}", {})
    assert len(first) == 36 and first != second
    assert render("{{$timestamp}}", {}).isdigit()


def test_null_is_an_error_where_nothing_can_be_left_out():
    with pytest.raises(TemplateError, match="style is null"):
        render("/beers/{{style}}/1", {"style": None})


def test_render_optional_leaves_out_a_whole_null_value():
    assert render_optional(" {{a}} ", {"a": None}) is None
    assert render_optional("{{a}}", {"a": "x"}) == "x"
    with pytest.raises(TemplateError, match="a is null"):
        render_optional("Bearer {{a}}", {"a": None})


def test_render_mapping_drops_null_entries_and_writes_literals_as_text():
    mapping = {"id": "{{id}}", "page": 2, "debug": True, "tag": "{{tag}}", "never": None}
    assert render_mapping(mapping, {"id": 7, "tag": None}) == {"id": "7", "page": "2", "debug": "true"}


def test_placeholders_lists_the_names_a_template_needs():
    assert placeholders("/{{a}}/{{ b.c }}?x={{a}}&t={{$uuid}}") == {"a", "b.c"}
