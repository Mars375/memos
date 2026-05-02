import subprocess
import sys
import tarfile
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_dev_extra_includes_pyarrow():
    pyproject = ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    dev_deps = data["project"]["optional-dependencies"]["dev"]

    assert any(dep.startswith("pyarrow") for dep in dev_deps)


def test_dev_extra_includes_build_for_artifact_smoke_tests():
    pyproject = ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    dev_deps = data["project"]["optional-dependencies"]["dev"]

    assert any(dep.startswith("build") for dep in dev_deps)


def test_project_version_matches_runtime_version():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    init_text = (ROOT / "src" / "memos" / "__init__.py").read_text()

    assert f'__version__ = "{data["project"]["version"]}"' in init_text


def test_console_script_entrypoint_targets_cli_main():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert data["project"]["scripts"]["memos"] == "memos.cli:main"


def test_project_metadata_declares_distribution_contract():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    project = data["project"]

    assert project["requires-python"] == ">=3.11"
    assert project["readme"] == "README.md"
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert data["build-system"]["requires"] == ["setuptools>=77.0", "wheel"]


def test_project_metadata_declares_urls_and_python_classifiers():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert data["project"]["urls"] == {
        "Homepage": "https://github.com/Mars375/memos",
        "Repository": "https://github.com/Mars375/memos",
        "Issues": "https://github.com/Mars375/memos/issues",
        "Changelog": "https://github.com/Mars375/memos/blob/main/CHANGELOG.md",
    }
    classifiers = set(data["project"]["classifiers"])
    assert "Programming Language :: Python :: 3.11" in classifiers
    assert "Programming Language :: Python :: 3.12" in classifiers
    assert "Programming Language :: Python :: 3.13" in classifiers


def test_docker_optional_extras_exist_in_project_metadata():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    extras = data["project"]["optional-dependencies"]

    for extra in ("server", "chroma", "parquet"):
        assert extra in extras
        assert extras[extra]


def test_dashboard_assets_are_packaged():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert data["tool"]["setuptools"]["package-data"]["memos.web"] == ["*.html", "*.css", "js/*.js"]


def test_built_artifacts_include_license_metadata_and_dashboard_assets(tmp_path):
    pytest.importorskip("build")
    dist_dir = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(dist_dir)],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    wheel = next(dist_dir.glob("*.whl"))
    sdist = next(dist_dir.glob("*.tar.gz"))

    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = Parser().parsestr(zf.read(metadata_name).decode("utf-8"))

    assert metadata["License-Expression"] == "MIT"
    assert any(name.endswith(".dist-info/licenses/LICENSE") for name in names)
    assert "memos/web/dashboard.html" in names
    assert "memos/web/dashboard.css" in names
    assert "memos/web/js/api.js" in names

    with tarfile.open(sdist) as tf:
        sdist_names = set(tf.getnames())

    assert any(name.endswith("/LICENSE") for name in sdist_names)
