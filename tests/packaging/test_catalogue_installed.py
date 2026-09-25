"""Packaged-install smoke test for the model & harness catalogue.

Builds the distribution, installs it into an isolated target directory, and
proves that ``catalogue.yaml`` ships as a packaged default and resolves from
the installed wheel in an unrelated working directory. The source-tree path
``Path(__file__).parents[4] / "config" / "catalogue.yaml"`` is gone: the
resolved default must live under ``skillweave/assets/`` inside the installed
package, never under a ``config/`` directory that only existed in the checkout.

Criterion 4 (SW152-007): catalogue.yaml ships as a packaged default and
resolves from an INSTALLED wheel in an unrelated working directory.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _build_and_install(target_dir: Path) -> Path:
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


def _run_catalogue_driver(target_dir: Path, foreign_cwd: Path, body: str) -> subprocess.CompletedProcess:
    site_dir = target_dir / "site"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(site_dir)
    driver = (
        "from pathlib import Path\n"
        "import skillweave.core.catalogue as cat\n"
        + body
    )
    return subprocess.run(
        [sys.executable, "-c", driver],
        cwd=str(foreign_cwd),
        env=env,
        capture_output=True,
        text=True,
    )


def test_catalogue_resolves_from_installed_wheel(tmp_path):
    """Criterion 4: the packaged default resolves inside the installed wheel,
    from an unrelated cwd, and no ``config/`` segment appears anywhere."""
    _build_and_install(tmp_path)
    src_pkg = (REPO_ROOT / "src" / "skillweave").resolve()

    foreign_cwd = tmp_path / "work"
    foreign_cwd.mkdir()

    body = (
        "p = cat._default_path().resolve()\n"
        "assert p.exists(), f'default catalogue missing: {p}'\n"
        "assert p.name == 'catalogue.yaml', p.name\n"
        "assert 'config' not in p.parts, f'config/ must be gone, got {p}'\n"
        "assert p.parts[-2] == 'assets', f'expected under skillweave/assets, got {p}'\n"
        "assert str(" + repr(str(src_pkg)) + ") not in str(p), 'must resolve from install, not source tree'\n"
        "d = cat.load_catalogue()\n"
        "assert set(('runtime', 'harnesses', 'models', 'role_defaults', 'contracts')).issubset(d)\n"
        "assert cat.get_model_for_role('reviewer') != cat.get_model_for_role('ops')\n"
        "print(p)\n"
    )
    proc = _run_catalogue_driver(tmp_path, foreign_cwd, body)
    assert proc.returncode == 0, proc.stderr

    # The source tree must no longer carry a config/ fallback at all.
    assert not (REPO_ROOT / "config").exists(), "config/ must be removed from the repository"


def test_parents4_source_path_is_gone(tmp_path):
    """The removed resolution never referenced parents[4]/config — that whole
    path family is absent from the installed default."""
    _build_and_install(tmp_path)

    foreign_cwd = tmp_path / "work"
    foreign_cwd.mkdir()

    body = (
        "p = cat._default_path().resolve()\n"
        "assert 'config' not in p.parts\n"
        "assert (Path(p).parent == Path(p).parent.resolve())\n"
        "print(p)\n"
    )
    proc = _run_catalogue_driver(tmp_path, foreign_cwd, body)
    assert proc.returncode == 0, proc.stderr
