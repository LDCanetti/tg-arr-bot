"""The running build's version.

The image's CI build passes it in as APP_VERSION (date plus commit, e.g.
2026.10.19-f078e43). Anything else — a local run, a hand-built image — is "dev".
"""

import os

APP_VERSION = os.environ.get("APP_VERSION") or "dev"
