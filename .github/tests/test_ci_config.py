"""Validation tests for GitHub Actions workflow and docker-compose.yml configuration."""

import pytest
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/release.yml"
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"

WORKFLOW_SERVICES = ["reclip", "bot", "dashboard"]
COMPOSE_SERVICES_WITH_BUILD = ["reclip", "bot", "dashboard"]


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Test 1: YAML parsing
# ---------------------------------------------------------------------------

class TestYAMLValid:
    def test_workflow_valid_yaml(self):
        result = load_yaml(WORKFLOW_PATH)
        assert isinstance(result, dict), "release.yml should parse to a dict"

    def test_compose_valid_yaml(self):
        result = load_yaml(COMPOSE_PATH)
        assert isinstance(result, dict), "docker-compose.yml should parse to a dict"


# ---------------------------------------------------------------------------
# Test 2: Matrix coverage
# ---------------------------------------------------------------------------

class TestMatrixCoverage:
    def test_matrix_service_contents(self):
        workflow = load_yaml(WORKFLOW_PATH)
        matrix = workflow["jobs"]["build-and-push"]["strategy"]["matrix"]
        assert "service" in matrix, "matrix must define 'service'"
        assert set(matrix["service"]) == set(WORKFLOW_SERVICES), (
            f"matrix.service must be exactly {WORKFLOW_SERVICES}, got {matrix['service']}"
        )

    def test_telegram_bot_api_not_in_matrix(self):
        workflow = load_yaml(WORKFLOW_PATH)
        matrix = workflow["jobs"]["build-and-push"]["strategy"]["matrix"]
        assert "telegram-bot-api" not in matrix.get("service", []), (
            "telegram-bot-api must not appear in matrix.service"
        )


# ---------------------------------------------------------------------------
# Test 3: Build context consistency
# ---------------------------------------------------------------------------

class TestBuildContextConsistency:
    def test_workflow_context_pattern(self):
        workflow = load_yaml(WORKFLOW_PATH)
        build_step = workflow["jobs"]["build-and-push"]["steps"][-1]
        assert "context" in build_step["with"], "build-push step must set context"
        assert build_step["with"]["context"] == "./${{ matrix.service }}", (
            f"workflow context must be './${{{{ matrix.service }}}}', "
            f"got {build_step['with']['context']!r}"
        )

    def test_compose_build_contexts_exist(self):
        compose = load_yaml(COMPOSE_PATH)
        for service in COMPOSE_SERVICES_WITH_BUILD:
            build_ctx = compose["services"][service].get("build", "")
            if build_ctx.startswith("./"):
                build_ctx = build_ctx[2:]
            assert build_ctx == service, (
                f"service '{service}' build context must be './{service}', "
                f"got {compose['services'][service].get('build')!r}"
            )


# ---------------------------------------------------------------------------
# Test 4: Image tag pattern
# ---------------------------------------------------------------------------

class TestImageTagPattern:
    def test_compose_images_use_ghcr(self):
        compose = load_yaml(COMPOSE_PATH)
        for service in COMPOSE_SERVICES_WITH_BUILD:
            image = compose["services"][service].get("image", "")
            assert image.startswith("ghcr.io/"), (
                f"service '{service}' image must start with 'ghcr.io/', got {image!r}"
            )

    def test_compose_images_use_tag_variable(self):
        compose = load_yaml(COMPOSE_PATH)
        for service in COMPOSE_SERVICES_WITH_BUILD:
            image = compose["services"][service].get("image", "")
            assert "${IMAGE_TAG:-latest}" in image, (
                f"service '{service}' image must include '${IMAGE_TAG:-latest}', got {image!r}"
            )

    def test_workflow_tags_ghcr_pattern(self):
        workflow = load_yaml(WORKFLOW_PATH)
        build_step = workflow["jobs"]["build-and-push"]["steps"][-1]
        # tags is a multi-line string, not a YAML list
        tags_raw = build_step["with"].get("tags", "")
        assert "ghcr.io/" in tags_raw, (
            f"workflow tags must include 'ghcr.io/', got:\n{tags_raw}"
        )
        assert ":${{ steps.version.outputs.version }}" in tags_raw, (
            f"workflow tags must include ':${{{{ steps.version.outputs.version }}}}', got:\n{tags_raw}"
        )
        assert ":latest" in tags_raw, (
            f"workflow tags must include ':latest', got:\n{tags_raw}"
        )


# ---------------------------------------------------------------------------
# Test 5: Prerelease skip
# ---------------------------------------------------------------------------

class TestPrereleaseSkip:
    def test_prerelease_skip_condition_exists(self):
        workflow = load_yaml(WORKFLOW_PATH)
        job = workflow["jobs"]["build-and-push"]
        assert "if" in job, "build-and-push job must have an 'if' condition"
        assert "!github.event.release.prerelease" in job["if"], (
            f"job 'if' must check '!github.event.release.prerelease', got {job['if']!r}"
        )
