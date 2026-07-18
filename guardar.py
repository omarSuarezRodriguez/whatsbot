"""Git save: add, commit (versión del README), push."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
README = ROOT / "README_PROMPTS.md"


def commit_message() -> str:
    if not README.is_file():
        raise FileNotFoundError(f"No se encontró {README}")
    first = README.read_text(encoding="utf-8").splitlines()[0].strip()
    if not first:
        raise ValueError("La primera línea de README.md está vacía.")
    return first.lstrip("#").strip()


def git(*args: str) -> None:
    result = subprocess.run(["git", *args], cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def git_capture(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    return (result.stdout or "").strip()


def current_branch() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    branch = (result.stdout or "").strip()
    if result.returncode != 0 or not branch:
        print("Error: no se pudo determinar la rama actual de Git.")
        raise SystemExit(1)
    return branch


def main() -> None:
    branch = current_branch()
    msg = commit_message()
    print(f"Commit: {msg!r}")
    if git_capture("status", "--porcelain"):
        git("add", ".")
        git("commit", "-m", msg)
    else:
        print("No hay cambios para hacer commit.")
    git("push", "-u", "origin", branch)
    print(f"Listo: add, commit y push completados en rama {branch!r}.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        print(f"\nTerminó con código {code}.")
        sys.exit(code)
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
