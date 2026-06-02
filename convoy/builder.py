"""
convoy.builder
Compiles a project into a .convoy bundle.
"""

import compileall
import importlib.util
import io
import os
import shutil
import struct
import sys
import tempfile
import time
import zlib
from pathlib import Path

CONVOY_MAGIC = b"CONVOY\x00\x01"  # magic header + format version


def _find_lib_path(lib_name: str) -> Path | None:
    """Locate an installed library's directory."""
    spec = importlib.util.find_spec(lib_name.split(".")[0])
    if spec is None:
        return None
    origin = spec.origin
    if origin is None:
        return None
    p = Path(origin)
    # package dir or single-file module
    if p.name == "__init__.py":
        return p.parent
    return p


def _collect_files(root: Path) -> list[tuple[Path, str]]:
    """Return (absolute_path, archive_name) for every file under root."""
    files = []
    for f in root.rglob("*"):
        if f.is_file():
            files.append((f, str(f.relative_to(root.parent))))
    return files


def build(project_dir: Path, toml_config: dict, out_path: Path, progress_cb=None):
    """
    Build a .convoy file from a project directory.

    progress_cb(message: str, percent: int) — optional progress callback.
    """

    def emit(msg, pct):
        if progress_cb:
            progress_cb(msg, pct)

    settings = toml_config.get("settings", [{}])
    if isinstance(settings, list):
        settings = settings[0] if settings else {}

    compression_level = int(settings.get("compression", 6))
    compression_level = max(1, min(9, compression_level))

    raw_libs = settings.get("libs", [])
    if isinstance(raw_libs, str):
        lib_names = [l.strip() for l in raw_libs.split(",")]
    else:
        lib_names = [l.strip() for l in raw_libs]

    file_section = toml_config.get("file", [{}])
    if isinstance(file_section, list):
        file_section = file_section[0] if file_section else {}
    main_file = file_section.get("main", "main.py")

    with tempfile.TemporaryDirectory(prefix="convoy_build_") as tmp:
        tmp = Path(tmp)
        stage = tmp / "stage"
        stage.mkdir()

        # ── 1. Copy project source ──────────────────────────────────────────
        emit("Gathering project files…", 5)
        proj_stage = stage / "project"
        shutil.copytree(project_dir, proj_stage, dirs_exist_ok=True)

        # ── 2. Compile .py → .pyc ───────────────────────────────────────────
        emit("Compiling Python sources…", 20)
        compileall.compile_dir(
            str(proj_stage),
            force=True,
            quiet=True,
            optimize=1,
        )
        # Keep .py sources so normal import machinery can find sibling modules

        # ── 3. Collect requested libraries ──────────────────────────────────
        emit("Collecting libraries…", 40)
        libs_stage = stage / "libs"
        libs_stage.mkdir()
        missing = []
        for lib in lib_names:
            lib_path = _find_lib_path(lib)
            if lib_path is None:
                missing.append(lib)
                continue
            dest = libs_stage / lib_path.name
            if lib_path.is_dir():
                shutil.copytree(lib_path, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(lib_path, dest)

        if missing:
            emit(f"WARNING: libs not found: {', '.join(missing)}", 45)

        # ── 4. Write manifest ────────────────────────────────────────────────
        emit("Writing manifest…", 55)
        manifest_lines = [
            f"main={main_file}",
            f"convoy_version=0.1.0",
            f"built={int(time.time())}",
            f"libs={','.join(lib_names)}",
        ]
        (stage / "MANIFEST").write_text("\n".join(manifest_lines))

        # ── 5. Pack everything into an in-memory tar-like blob, then compress ─
        emit("Packing bundle…", 65)
        raw_buf = io.BytesIO()
        all_files = _collect_files(stage)
        # write file count
        raw_buf.write(struct.pack(">I", len(all_files)))
        for abs_path, arc_name in all_files:
            data = abs_path.read_bytes()
            name_bytes = arc_name.encode()
            raw_buf.write(struct.pack(">H", len(name_bytes)))
            raw_buf.write(name_bytes)
            raw_buf.write(struct.pack(">I", len(data)))
            raw_buf.write(data)

        raw_bytes = raw_buf.getvalue()

        emit(f"Compressing (level {compression_level})…", 80)
        compressed = zlib.compress(raw_bytes, level=compression_level)

        # ── 6. Write .convoy file ────────────────────────────────────────────
        emit("Writing .convoy file…", 92)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(CONVOY_MAGIC)
            f.write(struct.pack(">I", len(compressed)))
            f.write(compressed)

        emit("Done!", 100)
        size_kb = out_path.stat().st_size / 1024
        return {
            "output": str(out_path),
            "size_kb": round(size_kb, 1),
            "files": len(all_files),
            "missing_libs": missing,
        }
