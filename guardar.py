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


def main() -> None:
    msg = commit_message()
    print(f"Commit: {msg!r}")
    git("add", ".")
    git("commit", "-m", msg)
    git("push", "-u", "origin", "main")
    print("Listo: add, commit y push completados.")


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
