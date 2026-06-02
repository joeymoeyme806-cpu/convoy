"""
convoy.runner
Extracts and runs a .convoy bundle in a private temp directory.
"""

import io
import os
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

from .builder import CONVOY_MAGIC


def run(convoy_path: Path, extra_args: list[str] = ()):
    """Extract convoy_path to a temp dir, run it, then wipe the temp dir."""

    with open(convoy_path, "rb") as f:
        magic = f.read(len(CONVOY_MAGIC))
        if magic != CONVOY_MAGIC:
            raise ValueError(f"{convoy_path} is not a valid .convoy file")
        (compressed_len,) = struct.unpack(">I", f.read(4))
        compressed = f.read(compressed_len)

    raw_bytes = zlib.decompress(compressed)
    buf = io.BytesIO(raw_bytes)

    (file_count,) = struct.unpack(">I", buf.read(4))

    with tempfile.TemporaryDirectory(prefix="convoy_run_") as tmp:
        tmp = Path(tmp)

        # ── Extract files ────────────────────────────────────────────────────
        for _ in range(file_count):
            (name_len,) = struct.unpack(">H", buf.read(2))
            arc_name = buf.read(name_len).decode()
            (data_len,) = struct.unpack(">I", buf.read(4))
            data = buf.read(data_len)

            dest = tmp / arc_name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)

        # ── Read manifest ────────────────────────────────────────────────────
        manifest_path = tmp / "stage" / "MANIFEST"
        manifest = {}
        if manifest_path.exists():
            for line in manifest_path.read_text().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    manifest[k.strip()] = v.strip()

        main_rel = manifest.get("main", "main.py")
        project_dir = tmp / "stage" / "project"
        libs_dir    = tmp / "stage" / "libs"

        # ── PYTHONPATH: project root + libs + every lib subdir ───────────────
        # This guarantees `import uiapp`, `import PySide6`, etc. all resolve
        extra_paths = [str(project_dir), str(libs_dir)]
        # Also add direct children of libs_dir (handles flat installs)
        for child in libs_dir.iterdir() if libs_dir.exists() else []:
            if child.is_dir():
                extra_paths.append(str(child.parent))
                break  # just need the libs root, already added above

        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(extra_paths + ([existing] if existing else []))

        # ── Find entry point ─────────────────────────────────────────────────
        # Prefer .py if present (keeps normal import machinery happy),
        # fall back to .pyc under __pycache__
        main_py = project_dir / main_rel
        if main_py.exists():
            entry = main_py
        else:
            entry = None
            stem = Path(main_rel).stem
            for pyc in project_dir.rglob("*.pyc"):
                if pyc.stem.startswith(stem):
                    entry = pyc
                    break

        if entry is None:
            raise FileNotFoundError(
                f"Could not find entry point '{main_rel}' in bundle"
            )

        result = subprocess.run(
            [sys.executable, str(entry), *extra_args],
            env=env,
        )

        # tmp dir wiped automatically — nothing stays on disk
        return result.returncode
