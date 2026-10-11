"""The file formats, exactly as a person writes them in meta.yaml, scenario files and project.yaml.

Every key a file may contain is a field here, so a typo or a wrong value is rejected
when the project is loaded rather than halfway through a test run.
"""

import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, WithJsonSchema, field_validator, model_validator


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
    def _seed_needs_random(self) -> DataSpec:
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


class Targets(_FileModel):
    """What counts as good enough. Reports say for every step whether its targets were met."""

    p95_ms: float | None = Field(
        default=None, gt=0, description="95% of the requests must take no longer than this many milliseconds."
    )
    p99_ms: float | None = Field(
        default=None, gt=0, description="99% of the requests must take no longer than this many milliseconds."
    )
    error_percent: float | None = Field(
        default=None, ge=0, le=100, description="No more than this percentage of the requests may fail."
    )

    def over(self, defaults: Targets) -> Targets:
        """These targets, with the defaults filling in whatever is not set here."""
        return Targets(**(defaults.model_dump(exclude_none=True) | self.model_dump(exclude_none=True)))


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
    targets: Targets = Field(
        default=Targets(),
        description="Response-time and failure targets for this endpoint; they override the targets in project.yaml.",
    )
    vars: dict[str, Any] = Field(default={}, description=_VARS)

    @field_validator("method", mode="before")
    @classmethod
    def _method_is_case_insensitive(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value


class StepFile(_FileModel):
    endpoint: str = Field(description="Name of a folder under endpoints/.")
    name: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Label for this step in reports, shown as scenario/name. Defaults to the endpoint name, "
            "numbered (#2, #3) when the endpoint is used more than once in the scenario."
        ),
    )
    vars: dict[str, Any] = Field(default={}, description=_VARS)


def _bare_names_are_steps(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    return [{"endpoint": item} if isinstance(item, str) else item for item in value]


_STEPS = "Each is an endpoint name, or a mapping to give the step a name or override vars."


class SetupFile(_FileModel):
    steps: list[StepFile] = Field(min_length=1, description="Endpoints to call once per virtual user. " + _STEPS)
    data: DataSpec | None = Field(
        default=None,
        description="One row per virtual user, for example its login: a CSV path, or a mapping with file and mode.",
    )

    _data_shorthand = field_validator("data", mode="before")(_path_is_shorthand)
    _step_shorthand = field_validator("steps", mode="before")(_bare_names_are_steps)


class ScenarioFile(_FileModel):
    """A scenario file: endpoints run in order as one test."""

    setup: SetupFile | None = Field(
        default=None,
        description=(
            "Steps run once per virtual user before its first iteration, such as a login. Their data row "
            "and extracted values are available in every iteration. A list of steps, or a mapping with "
            "steps and data."
        ),
    )
    steps: list[StepFile] = Field(
        min_length=1, description="Endpoints to call, in order, on every iteration. " + _STEPS
    )
    weight: int = Field(default=1, ge=1, description="How often this scenario is picked relative to the others.")
    data: DataSpec | None = Field(default=None, description=_DATA + " The row is shared by every step.")
    vars: dict[str, Any] = Field(default={}, description=_VARS)

    _data_shorthand = field_validator("data", mode="before")(_path_is_shorthand)
    _step_shorthand = field_validator("steps", mode="before")(_bare_names_are_steps)

    @field_validator("setup", mode="before")
    @classmethod
    def _list_is_setup_steps(cls, value: Any) -> Any:
        return {"steps": value} if isinstance(value, list) else value


_UNITS = {"s": 1, "m": 60, "h": 3600}


def _seconds(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smh])\s*", value)
    if not match:
        raise ValueError("expected a number of seconds, or a duration such as 30s, 5m or 1h")
    return float(match[1]) * _UNITS[match[2]]


Seconds = Annotated[
    float,
    BeforeValidator(_seconds),
    Field(ge=0),
    WithJsonSchema(
        {"anyOf": [{"type": "number", "minimum": 0}, {"type": "string", "pattern": r"^\s*\d+(\.\d+)?\s*[smh]\s*$"}]}
    ),
]
_PACING = (
    "Seconds from the start of one iteration to the start of the next, per virtual user. "
    "0 sends iterations back to back."
)


class BaselineSettings(_FileModel):
    users: int = Field(default=1, ge=1, description="Virtual users per scenario.")
    duration: Seconds = Field(default=60, description="How long to run: seconds, or a duration such as 30s or 5m.")
    pacing: Seconds = Field(default=1, description=_PACING)


class StopWhen(_FileModel):
    error_percent: float = Field(
        default=5, ge=0, le=100, description="Stop when more than this percentage of a step's requests fail."
    )
    p95_ms: float | None = Field(
        default=None, gt=0, description="Stop when a step's 95th percentile response time exceeds this many ms."
    )


class LimitSettings(_FileModel):
    start_users: int = Field(default=5, ge=1, description="Virtual users in the first step, across all scenarios.")
    step_users: int = Field(default=5, ge=1, description="Virtual users added in each further step.")
    max_users: int = Field(default=100, ge=1, description="Give up looking for the limit beyond this many users.")
    step_duration: Seconds = Field(default=30, description="How long each step runs before it is judged.")
    pacing: Seconds = Field(default=1, description=_PACING)
    stop_when: StopWhen = Field(default=StopWhen(), description="What counts as having reached the limit.")


class ModeSettings(_FileModel):
    baseline: BaselineSettings = Field(
        default=BaselineSettings(), description="Steady, light load to measure normal response times."
    )
    limit: LimitSettings = Field(
        default=LimitSettings(), description="Load raised in steps until the API fails or slows down."
    )


class ProjectFile(_FileModel):
    """project.yaml in the project folder: settings shared by every scenario. The file is optional."""

    name: str | None = Field(
        default=None,
        min_length=1,
        description="Name of the project in reports and report file names. Defaults to the folder's name.",
    )
    host: str | None = Field(
        default=None, description="Base URL of the API, e.g. https://api.example.com. --host overrides it."
    )
    verify_tls: bool = Field(
        default=True,
        description=(
            "Check the API's TLS certificate. Set false only for a test environment with a self-signed "
            "certificate: the connection is then encrypted but the server's identity is not verified."
        ),
    )
    vars: dict[str, Any] = Field(
        default={}, description="Values for {{placeholders}} in every scenario. Endpoint, scenario and step vars win."
    )
    targets: Targets = Field(
        default=Targets(),
        description="Response-time and failure targets for every endpoint that does not set its own.",
    )
    modes: ModeSettings = Field(default=ModeSettings(), description="Settings for `perfmon run --mode ...`.")
