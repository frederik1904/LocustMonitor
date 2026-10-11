import os
import sys

from perfmon.config.loader import load_project
from perfmon.config.models import ConfigError
from perfmon.users import build_user_classes

# Locust imports this file before it parses its own arguments, so the project folder comes from the environment.
try:
    project = load_project(os.environ.get("PERFMON_ROOT", "."))
    user_classes = build_user_classes(project)
except ConfigError as error:
    sys.exit(f"Configuration error: {error}")

# Locust finds user classes by looking at this module's globals.
globals().update(user_classes)
