import json
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ArchiveManifest:
    archived_paths: list[str]
    archive_date: str
    original_base: str
    archive_dir: str = ""
    restored: bool = False


def archive_paths(paths: list[str], archive_dir: str, dry_run: bool = True, base: Optional[str] = None) -> ArchiveManifest:
    if base is None:
        base = os.path.commonpath([os.path.abspath(p) for p in paths if os.path.exists(p)] or [os.path.abspath(".")])

    manifest = ArchiveManifest(
        archived_paths=[],
        archive_date=time.strftime("%Y-%m-%dT%H:%M:%S"),
        original_base=os.path.abspath(base),
        archive_dir=os.path.abspath(archive_dir),
    )

    os.makedirs(archive_dir, exist_ok=True)

    for src in paths:
        src_abs = os.path.abspath(src)
        if not os.path.exists(src_abs):
            continue
        rel = os.path.relpath(src_abs, start=base)
        dest = os.path.join(archive_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        if dry_run:
            manifest.archived_paths.append(src_abs)
        else:
            shutil.move(src_abs, dest)
            manifest.archived_paths.append(os.path.abspath(dest))

    manifest_path = os.path.join(archive_dir, "manifest.json")
    if not dry_run:
        _write_manifest(manifest, manifest_path)
    else:
        _preview_manifest(manifest, archive_dir)

    return manifest


def _write_manifest(manifest: ArchiveManifest, path: str):
    data = asdict(manifest)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _preview_manifest(manifest: ArchiveManifest, archive_dir: str):
    print(f"[DRY RUN] Would archive {len(manifest.archived_paths)} file(s) to {archive_dir}")
    print(f"[DRY RUN] Run with dry_run=False to execute")
    for p in manifest.archived_paths[:5]:
        print(f"  → {p}")
    if len(manifest.archived_paths) > 5:
        print(f"  ... and {len(manifest.archived_paths) - 5} more")


def read_manifest(manifest_path: str) -> ArchiveManifest:
    with open(manifest_path) as f:
        data = json.load(f)
    return ArchiveManifest(**data)


def restore_from_manifest(manifest: ArchiveManifest) -> bool:
    if manifest.restored:
        print("Manifest already restored. Skipping.")
        return False

    success = True
    for archived in manifest.archived_paths:
        if not os.path.exists(archived):
            print(f"  WARN: {archived} not found in archive, skipping")
            continue
        rel = os.path.relpath(archived, start=manifest.archive_dir)
        dest = os.path.join(manifest.original_base, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(archived, dest)
        print(f"  Restored: {archived} → {dest}")

    manifest.restored = True
    return success
