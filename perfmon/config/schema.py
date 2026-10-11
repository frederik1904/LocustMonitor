"""The file formats, exactly as a person writes them in meta.yaml and scenario files.

Every key a file may contain is a field here, so a typo or a wrong value is rejected
when the project is loaded rather than halfway through a test run.
"""

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ApiProtocol(StrEnum):
    REST = "rest"


class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class BodyMatch(StrEnum):
    NONE = "none"
    SUBSET = "subset"
    EXACT = "exact"


class DataMode(StrEnum):
    SHARED = "shared"
    SCENARIO = "scenario"
    RANDOM = "random"


class _FileModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, coerce_numbers_to_str=True)


class ValidationSpec(_FileModel):
    status: int | None = Field(default=None, description="Expected HTTP status code.")
    body: BodyMatch = Field(
        default=BodyMatch.NONE,
        description=(
            "How the response body is compared with the response file. "
            "none: not at all. "
            "subset: everything in the file must be in the response, which may have more keys and more list items. "
            "exact: the response must equal the file."
        ),
    )


class DataSpec(_FileModel):
    file: Path = Field(description="CSV file, relative to the project folder. An empty cell leaves the value out.")
    mode: DataMode = Field(
        default=DataMode.SHARED,
        description=(
            "shared: one cursor per file, shared by every scenario using it. "
            "scenario: this scenario has its own cursor. "
            "random: like shared, with the rows shuffled once."
        ),
    )
    seed: int | None = Field(default=None, description="Makes the shuffle of mode: random repeatable.")

    @model_validator(mode="after")
    def _seed_needs_random(self) -> "DataSpec":
        if self.seed is not None and self.mode is not DataMode.RANDOM:
            raise ValueError("seed only applies to mode: random")
        return self


def _path_is_shorthand(value: Any) -> Any:
    return {"file": value} if isinstance(value, str) else value


_VARS = (
    "Values for {{placeholders}}. The most specific wins: step, then scenario, then endpoint; "
    "data rows and extracted values come on top. A null value leaves the header, query parameter "
    "or JSON value it fills out of the request."
)
_DATA = "One row of placeholder values per iteration: a CSV path, or a mapping with file and mode."


class EndpointFile(_FileModel):
    """An endpoint's meta.yaml. Endpoints are building blocks: only scenarios run."""

    path: str = Field(description="URL path, e.g. /orders/{{order_id}}.")
    protocol: ApiProtocol = Field(default=ApiProtocol.REST, description="API style of the endpoint.")
    method: HttpMethod = Field(default=HttpMethod.GET, description="HTTP method.")
    query: dict[str, str | int | float | bool | None] = Field(
        default={},
        description="Query string parameters; values may use {{placeholders}}. A null value is not sent.",
    )
    headers: dict[str, str] = Field(default={}, description="Request headers; values may use {{placeholders}}.")
    extract: dict[str, str] = Field(
        default={},
        description="Values to take from the response for later steps: variable name to JSONPath.",
    )
    # Written as `validate:` in the file; BaseModel already has a `validate` attribute.
    validation: ValidationSpec | None = Field(
        default=None,
        alias="validate",
        description="Checks on the response. Without it, only connection errors and status >= 400 fail.",
    )
    vars: dict[str, Any] = Field(default={}, description=_VARS)

    @field_validator("method", mode="before")
    @classmethod
    def _method_is_case_insensitive(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value


class StepFile(_FileModel):
    endpoint: str = Field(description="Name of a folder under endpoints/.")
    vars: dict[str, Any] = Field(default={}, description=_VARS)


class ScenarioFile(_FileModel):
    """A scenario file: endpoints run in order as one test."""

    steps: list[StepFile] = Field(
        min_length=1,
        description="Endpoints to call, in order. Each is an endpoint name, or a mapping to override vars.",
    )
    weight: int = Field(default=1, ge=1, description="How often this scenario is picked relative to the others.")
    data: DataSpec | None = Field(default=None, description=_DATA + " The row is shared by every step.")
    vars: dict[str, Any] = Field(default={}, description=_VARS)

    _data_shorthand = field_validator("data", mode="before")(_path_is_shorthand)

    @field_validator("steps", mode="before")
    @classmethod
    def _bare_name_is_a_step(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        return [{"endpoint": item} if isinstance(item, str) else item for item in value]
