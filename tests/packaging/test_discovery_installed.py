"""
Packaged-install smoke tests for Discovery & Design Thinking.

These tests build the skillweave distribution, install it into an isolated
target directory, and exercise discovery *from the installed package* in a
fresh interpreter launched from an unrelated working directory. Neither the
repository source tree nor the repository `.skillweave/lib` directory is ever
on the subprocess import path, so the imported modules prove to have been
installed, not re-imported from the checkout.

Two things are proven here that the source-tree suite cannot:

* criterion 4: a missing packaged discovery asset fails explicitly with the
  resolved expected path, rather than falling back to another checkout rooted
  at the caller's working directory.
* criterion 6: discovery imports and runs from the installed package without
  the source tree or repository `.skillweave/lib` on ``sys.path``.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _build_and_install(target_dir: Path) -> Path:
    """Build the distribution and install it into an isolated target dir.

    Uses a throwaway virtualenv for the build so the environment's own
    site-packages cannot leak an editable install or other broken state
    into the build. Returns the installed ``skillweave`` package directory.
    """
    venv_dir = target_dir / "builder"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    pip = venv_dir / "bin" / "pip"
    subprocess.run(
        [str(pip), "install", "--no-deps", "--target", str(target_dir / "site"), str(REPO_ROOT)],
        check=True,
        capture_output=True,
        text=True,
    )
    pkg_dir = target_dir / "site" / "skillweave"
    assert pkg_dir.is_dir(), f"installed skillweave package missing at {pkg_dir}"
    return pkg_dir


_IMPORT_LINE = (
    "import json, os, sys, tempfile\n"
    "from pathlib import Path\n"
    "import skillweave\n"
    "from skillweave.design_thinking import (\n"
    "    DesignThinkingLens, resolve_discovery_asset, DiscoveryAssetNotFound,\n"
    ")\n"
    "from skillweave.persistence import SkillWeavePersistence\n"
)

_EXERCISE_LINE = (
    "root = Path(os.environ['SW_INSTALLED_ROOT'])\n"
    "assert str(Path(root)) in sys.path, sys.path\n"
)


def _run_driver(target_dir: Path, foreign_cwd: Path, body: str) -> subprocess.CompletedProcess:
    site_dir = target_dir / "site"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(site_dir)
    env["SW_INSTALLED_ROOT"] = str(site_dir)
    driver = _IMPORT_LINE + _EXERCISE_LINE + body
    return subprocess.run(
        [sys.executable, "-c", driver],
        cwd=str(foreign_cwd),
        env=env,
        capture_output=True,
        text=True,
    )


def test_installed_discovery_imports_and_runs(tmp_path):
    """Criterion 6: installed package imports and exercises discovery without the
    source tree or repository `.skillweave/lib` on sys.path."""
    pkg_dir = _build_and_install(tmp_path)
    installed_path = pkg_dir.resolve()
    assert (pkg_dir / ".skillweave").exists() is False
    assert (pkg_dir / "ideation.py").exists() is False
    assert (pkg_dir / "assumptions.py").exists() is False

    site = (tmp_path / "site").resolve()
    src_pkg = (REPO_ROOT / "src" / "skillweave").resolve()
    assert installed_path != src_pkg

    foreign_cwd = tmp_path / "work"
    foreign_cwd.mkdir()

    body = (
        "assert Path(skillweave.__file__).resolve() != "
        + repr(str(src_pkg))
        + " + '/__init__.py'\n"
        "with tempfile.TemporaryDirectory() as td:\n"
        "    p = SkillWeavePersistence(td)\n"
        "    p.ensure_folder_structure()\n"
        "    cfg = p.load_config()\n"
        "    cfg.features['design_thinking_lens'] = True\n"
        "    p.save_config(cfg)\n"
        "    lens = DesignThinkingLens(td)\n"
        "    result = lens.apply_to_content('blueprint', 'Paragraph one.</Paragraph>\\n', 'text')\n"
        "    assert 'enabled' in result\n"
    )
    proc = _run_driver(tmp_path, foreign_cwd, body)
    assert proc.returncode == 0, proc.stderr


def test_installed_discovery_missing_asset_fails_explicit(tmp_path):
    """Criterion 4: missing packaged discovery assets fail explicitly with the
    resolved expected path rather than falling back to another checkout."""
    _build_and_install(tmp_path)
    site = (tmp_path / "site").resolve()
    expected = (site / ".skillweave" / "lenses" / "design-thinking.yaml").resolve()

    foreign_cwd = tmp_path / "work"
    foreign_cwd.mkdir()

    body = (
        "try:\n"
        "    resolve_discovery_asset(root, 'lenses', 'design-thinking.yaml')\n"
        "    raise SystemExit('expected DiscoveryAssetNotFound')\n"
        "except DiscoveryAssetNotFound as exc:\n"
        "    assert exc.expected_path == Path("
        + repr(str(expected))
        + ").resolve(), (exc.expected_path, "
        + repr(str(expected))
        + ")\n"
        "    assert str(exc.expected_path) in str(exc)\n"
        "    assert exc.expected_path.anchor and '.skillweave' in exc.expected_path.parts\n"
    )
    proc = _run_driver(tmp_path, foreign_cwd, body)
    assert proc.returncode == 0, proc.stderr
