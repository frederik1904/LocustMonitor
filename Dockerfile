# Build stage: install the locked dependencies and perfmon itself into a virtual environment.
FROM python:3.14-slim AS build
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, so changing the code does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY perfmon ./perfmon
RUN uv sync --frozen --no-dev --no-editable

# Run stage: only Python and the virtual environment.
FROM python:3.14-slim
RUN useradd --create-home perfmon
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER perfmon
# The project folder (endpoints/, scenarios/, project.yaml) is mounted here.
WORKDIR /project
ENTRYPOINT ["perfmon"]
CMD ["--help"]
