"""Portable structural deployment checks; not a substitute for Docker/Bicep execution."""

import json

import yaml

from src.config import ROOT


def validate():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    assert {"db", "init", "api"} <= compose["services"].keys()
    api = compose["services"]["api"]
    assert "@db:5432" in api["environment"]["DATABASE_URL"]
    assert "ADMIN_DATABASE_URL" not in api["environment"]
    assert api["depends_on"]["init"]["condition"] == "service_completed_successfully"
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        # BaseLoader avoids YAML 1.1 parsing GitHub's `on` as boolean True.
        workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        assert workflow["on"] and workflow["jobs"]
        assert workflow["permissions"]["contents"] == "read"
    deploy = yaml.load(
        (ROOT / ".github/workflows/deploy-staging.yml").read_text(), Loader=yaml.BaseLoader
    )
    job = deploy["jobs"]["deploy"]
    assert job["environment"] == "staging" and job["permissions"]["id-token"] == "write"
    assert "head_branch == 'main'" in job["if"] and "conclusion == 'success'" in job["if"]
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "USER appuser" in dockerfile and "--reload" not in dockerfile
    assert "constraints.txt" in dockerfile
    json.loads((ROOT / "infra/staging.parameters.example.json").read_text())
    print("Compose, workflow, Dockerfile and parameter structural checks passed")


if __name__ == "__main__":
    validate()
