import pytest

from perfmon.protocols.json_compare import describe_differences

ACTUAL = {"id": 1, "name": "IPA", "rating": {"average": 4.4, "reviews": 9}, "tags": ["a", "b", "c"], "ok": True}


@pytest.mark.parametrize(
    "expected",
    [
        {},
        {"id": 1},
        {"id": 1.0, "rating": {"reviews": 9}},
        {"tags": ["a", "b"]},  # extra items after the expected ones are fine
        {"tags": []},
    ],
)
def test_subset_matches_when_the_response_has_at_least_the_expected(expected):
    assert describe_differences(expected, ACTUAL, exact=False) is None


@pytest.mark.parametrize(
    ("expected", "message"),
    [
        ({"id": 2}, "$.id expected 2, got 1"),
        ({"price": 1}, "$.price is missing"),
        ({"rating": {"average": 5}}, "$.rating.average expected 5, got 4.4"),
        ({"rating": 4}, '$.rating expected 4, got {"average": 4.4, "reviews": 9}'),
        ({"id": {"x": 1}}, "$.id expected an object, got 1"),
        ({"tags": ["a", "x"]}, '$.tags[1] expected "x", got "b"'),
        ({"tags": ["a", "b", "c", "d"]}, "$.tags expected at least 4 items, got 3"),
        ({"id": [1]}, "$.id expected a list, got 1"),
        ({"ok": 1}, "$.ok expected 1, got true"),
        ({"id": "1"}, '$.id expected "1", got 1'),
    ],
)
def test_subset_differences_name_the_place(expected, message):
    assert describe_differences(expected, ACTUAL, exact=False) == message


def test_exact_rejects_extras():
    assert describe_differences(dict(ACTUAL), ACTUAL, exact=True) is None
    assert describe_differences({"a": 1}, {"a": 1, "b": 2}, exact=True) == "$.b is not expected"
    assert describe_differences([1], [1, 2], exact=True) == "$ expected 1 items, got 2"
    assert describe_differences([{"a": 1}], [{"a": 1, "b": 2}], exact=True) == "$[0].b is not expected"


def test_only_the_first_differences_are_listed_and_long_values_are_cut():
    message = describe_differences({"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}, {}, exact=False)
    assert message == "$.a is missing; $.b is missing; $.c is missing (and 2 more)"
    assert describe_differences({"a": 1}, {"a": "x" * 200}, exact=False) == '$.a expected 1, got "' + "x" * 56 + "..."
