"""Local filesystem paths used by the deploy, resolved from this file's
location so the deploy behaves the same whichever directory you run it from."""

from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent
PROJECT_DIR = DEPLOY_DIR.parent

TEMPLATES_DIR = DEPLOY_DIR / "templates"
ARTIFACTS_DIR = DEPLOY_DIR / ".artifacts"
