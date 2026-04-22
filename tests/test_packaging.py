import tomllib
from pathlib import Path


def test_dev_extra_includes_pyarrow():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())
    dev_deps = data["project"]["optional-dependencies"]["dev"]

    assert any(dep.startswith("pyarrow") for dep in dev_deps)
