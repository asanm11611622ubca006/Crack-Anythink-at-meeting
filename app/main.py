from __future__ import annotations

import os
import sys
from pathlib import Path

from .config import load_config
from .ui import CaptionExplainerApp


def ensure_tk_runtime() -> None:
    project_root = Path(__file__).resolve().parent.parent
    python_root = Path(sys.executable).resolve().parent

    candidate_tcl = [
        project_root / "vendor" / "tcl" / "tcl8.6",
        python_root / "tcl" / "tcl8.6",
    ]
    candidate_tk = [
        project_root / "vendor" / "tcl" / "tk8.6",
        python_root / "tcl" / "tk8.6",
    ]

    if not os.getenv("TCL_LIBRARY"):
        for path in candidate_tcl:
            if path.exists():
                os.environ["TCL_LIBRARY"] = str(path)
                break

    if not os.getenv("TK_LIBRARY"):
        for path in candidate_tk:
            if path.exists():
                os.environ["TK_LIBRARY"] = str(path)
                break


def main() -> None:
    ensure_tk_runtime()
    from tkinter import TclError, Tk

    try:
        config = load_config()
        root = Tk()
    except TclError as exc:
        raise SystemExit(
            "Tkinter could not start. Reinstall Python with Tcl/Tk support, or set TCL_LIBRARY and TK_LIBRARY before running."
        ) from exc

    CaptionExplainerApp(root, config)
    root.mainloop()


if __name__ == "__main__":
    main()
