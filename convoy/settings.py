"""
convoy.settings
The `convoy-settings` command — a small tkinter GUI for managing convoy.toml
and viewing build output.
"""

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

# ── Colours ──────────────────────────────────────────────────────────────────
BG       = "#0f0f0f"
BG2      = "#1a1a1a"
BG3      = "#242424"
ACCENT   = "#f5c518"
FG       = "#e8e8e8"
FG_DIM   = "#888888"
RED      = "#e05555"
GREEN    = "#55c97a"
FONT     = ("Consolas", 10)
FONT_SM  = ("Consolas", 9)
FONT_BIG = ("Consolas", 13, "bold")


class ConvoySettings(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("convoy-settings")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(700, 520)

        self._build_ui()
        self._load_toml()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=BG, pady=8)
        hdr.pack(fill="x", padx=16)
        tk.Label(hdr, text="⬛ CONVOY", font=FONT_BIG,
                 bg=BG, fg=ACCENT).pack(side="left")
        tk.Label(hdr, text="settings & toml builder", font=FONT_SM,
                 bg=BG, fg=FG_DIM).pack(side="left", padx=10)

        sep = tk.Frame(self, bg=ACCENT, height=1)
        sep.pack(fill="x")

        # Main notebook
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=0, pady=0)

        self._style_notebook(nb)

        self.tab_builder = tk.Frame(nb, bg=BG2)
        self.tab_terminal = tk.Frame(nb, bg=BG2)
        nb.add(self.tab_builder,  text="  TOML Builder  ")
        nb.add(self.tab_terminal, text="  Terminal  ")

        self._build_builder_tab()
        self._build_terminal_tab()

        # Bottom bar
        bar = tk.Frame(self, bg=BG3, pady=6)
        bar.pack(fill="x", side="bottom")
        self._btn(bar, "💾  Save convoy.toml", self._save_toml).pack(side="left", padx=12)
        self._btn(bar, "🔨  Build", self._run_build).pack(side="left")
        self._btn(bar, "▶  Run last", self._run_last).pack(side="left", padx=8)
        tk.Label(bar, text="convoy v0.1.0", font=FONT_SM,
                 bg=BG3, fg=FG_DIM).pack(side="right", padx=12)

    def _build_builder_tab(self):
        f = self.tab_builder
        pad = {"padx": 16, "pady": 6}

        # ── [[file]] section ─────────────────────────────────────────────────
        self._section(f, "[[file]]")

        row = tk.Frame(f, bg=BG2)
        row.pack(fill="x", **pad)
        tk.Label(row, text="main", width=14, anchor="w",
                 font=FONT, bg=BG2, fg=FG_DIM).pack(side="left")
        self.var_main = tk.StringVar(value="main.py")
        entry = self._entry(row, self.var_main, width=36)
        entry.pack(side="left")
        self._btn(row, "Browse", self._browse_main, small=True).pack(side="left", padx=6)

        # ── [[settings]] section ─────────────────────────────────────────────
        self._section(f, "[[settings]]")

        row2 = tk.Frame(f, bg=BG2)
        row2.pack(fill="x", **pad)
        tk.Label(row2, text="compression", width=14, anchor="w",
                 font=FONT, bg=BG2, fg=FG_DIM).pack(side="left")
        self.var_compression = tk.IntVar(value=6)
        scale = tk.Scale(
            row2, from_=1, to=9, orient="horizontal",
            variable=self.var_compression,
            bg=BG2, fg=FG, troughcolor=BG3,
            activebackground=ACCENT, highlightthickness=0,
            font=FONT_SM, length=200, showvalue=True,
        )
        scale.pack(side="left")
        tk.Label(row2, text="1=fast  9=smallest",
                 font=FONT_SM, bg=BG2, fg=FG_DIM).pack(side="left", padx=8)

        row3 = tk.Frame(f, bg=BG2)
        row3.pack(fill="x", **pad)
        tk.Label(row3, text="libs", width=14, anchor="w",
                 font=FONT, bg=BG2, fg=FG_DIM).pack(side="left")
        self.var_libs = tk.StringVar()
        self._entry(row3, self.var_libs, width=46).pack(side="left")
        tk.Label(row3, text="comma-separated",
                 font=FONT_SM, bg=BG2, fg=FG_DIM).pack(side="left", padx=8)

        # ── Live TOML preview ────────────────────────────────────────────────
        self._section(f, "Preview")
        self.toml_preview = scrolledtext.ScrolledText(
            f, height=8, font=FONT_SM,
            bg=BG3, fg=ACCENT, insertbackground=ACCENT,
            relief="flat", bd=0,
        )
        self.toml_preview.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # Bind changes → update preview
        for var in (self.var_main, self.var_libs):
            var.trace_add("write", lambda *_: self._update_preview())
        self.var_compression.trace_add("write", lambda *_: self._update_preview())
        self._update_preview()

    def _build_terminal_tab(self):
        f = self.tab_terminal
        self.terminal = scrolledtext.ScrolledText(
            f, font=FONT_SM,
            bg="#080808", fg=GREEN, insertbackground=GREEN,
            relief="flat", bd=0, state="disabled",
        )
        self.terminal.pack(fill="both", expand=True, padx=0, pady=0)
        self.terminal.tag_config("err",    foreground=RED)
        self.terminal.tag_config("accent", foreground=ACCENT)
        self.terminal.tag_config("dim",    foreground=FG_DIM)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _section(self, parent, label):
        row = tk.Frame(parent, bg=BG2)
        row.pack(fill="x", padx=16, pady=(12, 2))
        tk.Label(row, text=label, font=("Consolas", 10, "bold"),
                 bg=BG2, fg=ACCENT).pack(side="left")
        tk.Frame(row, bg=BG3, height=1).pack(side="left", fill="x", expand=True, padx=8)

    def _entry(self, parent, textvariable, width=30):
        return tk.Entry(
            parent, textvariable=textvariable, width=width,
            font=FONT, bg=BG3, fg=FG, insertbackground=FG,
            relief="flat", bd=4,
        )

    def _btn(self, parent, text, cmd, small=False):
        f = FONT_SM if small else FONT
        return tk.Button(
            parent, text=text, command=cmd,
            font=f, bg=BG3, fg=ACCENT,
            activebackground=ACCENT, activeforeground=BG,
            relief="flat", bd=0, padx=10, pady=4,
            cursor="hand2",
        )

    def _style_notebook(self, nb):
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("TNotebook",        background=BG,  borderwidth=0)
        style.configure("TNotebook.Tab",    background=BG3, foreground=FG_DIM,
                        font=FONT, padding=[12, 5])
        style.map("TNotebook.Tab",
                  background=[("selected", BG2)],
                  foreground=[("selected", ACCENT)])

    # ── TOML ──────────────────────────────────────────────────────────────────

    def _update_preview(self):
        libs = self.var_libs.get().strip()
        libs_line = f'libs = "{libs}"' if libs else '# libs = "pyside6, PIL"'
        preview = (
            "[[file]]\n"
            f'main = "{self.var_main.get()}"\n\n'
            "[[settings]]\n"
            f"compression = {self.var_compression.get()}\n"
            f"{libs_line}\n"
        )
        self.toml_preview.config(state="normal")
        self.toml_preview.delete("1.0", "end")
        self.toml_preview.insert("end", preview)
        self.toml_preview.config(state="disabled")

    def _save_toml(self):
        libs = self.var_libs.get().strip()
        libs_line = f'libs = "{libs}"\n' if libs else ""
        content = (
            "[[file]]\n"
            f'main = "{self.var_main.get()}"\n\n'
            "[[settings]]\n"
            f"compression = {self.var_compression.get()}\n"
            + libs_line
        )
        path = Path("convoy.toml")
        path.write_text(content)
        messagebox.showinfo("Saved", f"convoy.toml saved to:\n{path.resolve()}")

    def _load_toml(self):
        path = Path("convoy.toml")
        if not path.exists() or tomllib is None:
            return
        try:
            with open(path, "rb") as f:
                cfg = tomllib.load(f)
            fs = cfg.get("file", [{}])
            fs = fs[0] if isinstance(fs, list) and fs else fs
            ss = cfg.get("settings", [{}])
            ss = ss[0] if isinstance(ss, list) and ss else ss

            self.var_main.set(fs.get("main", "main.py"))
            self.var_compression.set(int(ss.get("compression", 6)))
            libs = ss.get("libs", "")
            if isinstance(libs, list):
                libs = ", ".join(libs)
            self.var_libs.set(libs)
        except Exception:
            pass

    def _browse_main(self):
        path = filedialog.askopenfilename(
            title="Select main Python file",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")],
        )
        if path:
            self.var_main.set(Path(path).name)

    # ── Build / Run ───────────────────────────────────────────────────────────

    def _term_write(self, text, tag=None):
        self.terminal.config(state="normal")
        self.terminal.insert("end", text, tag or "")
        self.terminal.see("end")
        self.terminal.config(state="disabled")

    def _run_build(self):
        self._save_toml()
        # Switch to terminal tab (index 1)
        self.nametowidget(self.winfo_children()[2]).select(1)  # notebook
        self._term_write("\n── convoy build ──\n", "accent")

        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "convoy.cli", "build", "--fast"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True,
            )
            for line in proc.stdout:
                tag = "err" if "error" in line.lower() or "warning" in line.lower() else None
                self._term_write(line, tag)
            proc.wait()
            color = "accent" if proc.returncode == 0 else "err"
            self._term_write(f"\nExit code: {proc.returncode}\n", color)
        except Exception as e:
            self._term_write(f"Failed to run build: {e}\n", "err")

    def _run_last(self):
        # Find the most recently modified .convoy file
        convoys = sorted(Path(".").glob("*.convoy"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not convoys:
            messagebox.showwarning("No .convoy file", "Build a project first.")
            return
        target = convoys[0]
        self.nametowidget(self.winfo_children()[2]).select(1)
        self._term_write(f"\n── convoy run {target} ──\n", "accent")
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "convoy.cli", "run", str(target)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True,
            )
            for line in proc.stdout:
                self._term_write(line)
            proc.wait()
            self._term_write(f"\nExit code: {proc.returncode}\n", "accent")
        except Exception as e:
            self._term_write(f"Failed: {e}\n", "err")


def main():
    app = ConvoySettings()
    app.mainloop()


if __name__ == "__main__":
    main()
