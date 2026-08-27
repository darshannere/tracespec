from pathlib import Path


DOCKERFILE = Path("Dockerfile").read_text()


def test_dockerfile_builds_dashboard_only_when_web_exists():
    assert "if [ -f web/package.json ]" in DOCKERFILE
    assert "npm --prefix web run build" in DOCKERFILE


def test_dockerfile_copies_dashboard_for_installed_package():
    assert 'sysconfig.get_path("purelib")' in DOCKERFILE
    assert "shutil.copytree" in DOCKERFILE


def test_dockerignore_excludes_secrets_dependencies_and_build_artifacts():
    ignored = set(Path(".dockerignore").read_text().splitlines())

    assert {".env", ".venv/", "*.db", "node_modules/", "web/dist/"} <= ignored
