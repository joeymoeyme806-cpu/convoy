"""
convoy.cli
The main `convoy` command.
"""

import sys
import time
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.text import Text
from rich import print as rprint

console = Console()

BANNER = """[bold yellow]
  ██████╗ ██████╗ ███╗  ██╗██╗   ██╗ ██████╗ ██╗   ██╗
 ██╔════╝██╔═══██╗████╗ ██║██║   ██║██╔═══██╗╚██╗ ██╔╝
 ██║     ██║   ██║██╔██╗██║██║   ██║██║   ██║ ╚████╔╝ 
 ██║     ██║   ██║██║╚████║╚██╗ ██╔╝██║   ██║  ╚██╔╝  
 ╚██████╗╚██████╔╝██║ ╚███║ ╚████╔╝ ╚██████╔╝   ██║   
  ╚═════╝ ╚═════╝ ╚═╝  ╚══╝  ╚═══╝   ╚═════╝    ╚═╝   
[/bold yellow][dim]  pack your project. ship it whole.[/dim]
"""


def cmd_build(args: list[str], fast: bool):
    if tomllib is None:
        console.print("[red]Error:[/red] tomllib not available. Install tomli for Python <3.11.")
        sys.exit(1)

    from .builder import build

    # Find convoy.toml
    toml_path = Path("convoy.toml")
    if not toml_path.exists():
        console.print("[red]Error:[/red] No convoy.toml found in current directory.")
        console.print("  Run [bold]convoy-settings[/bold] to create one.")
        sys.exit(1)

    with open(toml_path, "rb") as f:
        config = tomllib.load(f)

    file_section = config.get("file", [{}])
    if isinstance(file_section, list):
        file_section = file_section[0] if file_section else {}
    main_file = file_section.get("main", "main.py")

    out_name = Path(main_file).stem + ".convoy"
    out_path = Path(out_name)

    if not fast:
        console.print(BANNER)
        console.print(
            Panel(
                f"[bold]Main:[/bold] {main_file}\n[bold]Output:[/bold] {out_name}",
                title="[yellow]BUILD[/yellow]",
                border_style="yellow",
            )
        )

    last_msg = [""]

    def progress_cb(msg, pct):
        last_msg[0] = msg
        if fast:
            return
        # handled by progress bar below

    if fast:
        result = build(Path("."), config, out_path, progress_cb=progress_cb)
        console.print(
            f"[green]✓[/green] Built [bold]{result['output']}[/bold] "
            f"({result['size_kb']} KB, {result['files']} files)"
        )
    else:
        with Progress(
            SpinnerColumn(spinner_name="dots", style="yellow"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=30, style="yellow", complete_style="bright_yellow"),
            TaskProgressColumn(),
            console=console,
            transient=False,
        ) as prog:
            task = prog.add_task("Starting…", total=100)

            def rich_progress_cb(msg, pct):
                prog.update(task, completed=pct, description=msg)

            result = build(Path("."), config, out_path, progress_cb=rich_progress_cb)

        if result["missing_libs"]:
            console.print(
                f"[yellow]⚠[/yellow]  Missing libs (not bundled): "
                f"{', '.join(result['missing_libs'])}"
            )

        console.print(
            Panel(
                f"[green]✓[/green]  [bold]{result['output']}[/bold]\n"
                f"   {result['size_kb']} KB  ·  {result['files']} files packed",
                title="[green]CONVOY READY[/green]",
                border_style="green",
            )
        )


def cmd_run(args: list[str], fast: bool):
    from .runner import run

    if not args:
        console.print("[red]Error:[/red] specify a .convoy file.  convoy run <file.convoy>")
        sys.exit(1)

    convoy_file = Path(args[0])
    extra = args[1:]

    if not convoy_file.exists():
        console.print(f"[red]Error:[/red] File not found: {convoy_file}")
        sys.exit(1)

    if not fast:
        console.print(f"[yellow]▶[/yellow]  Loading [bold]{convoy_file}[/bold]…")

    code = run(convoy_file, extra_args=extra)
    sys.exit(code)


def cmd_help():
    console.print(BANNER)
    console.print(
        Panel(
            "[bold yellow]convoy build[/bold yellow]          Build a .convoy from convoy.toml\n"
            "[bold yellow]convoy run <file>[/bold yellow]     Run a .convoy bundle\n\n"
            "[dim]Flags:[/dim]\n"
            "  [bold]--fast[/bold]   Skip animations and decorations\n\n"
            "[dim]Run [bold]convoy-settings[/bold] to open the settings & TOML builder.[/dim]",
            title="[yellow]CONVOY[/yellow]",
            border_style="yellow",
        )
    )


def main():
    argv = sys.argv[1:]
    fast = "--fast" in argv
    argv = [a for a in argv if a != "--fast"]

    if not argv or argv[0] in ("help", "--help", "-h"):
        cmd_help()
    elif argv[0] == "build":
        cmd_build(argv[1:], fast)
    elif argv[0] == "run":
        cmd_run(argv[1:], fast)
    else:
        console.print(f"[red]Unknown command:[/red] {argv[0]}")
        cmd_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
