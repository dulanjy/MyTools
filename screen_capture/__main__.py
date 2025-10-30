"""Module execution entry point.

Normal usage:
    python -m screen_capture

Fallback (not recommended but supported):
    python screen_capture/__main__.py

When executed directly as a script there is no package parent, so we
gracefully degrade to absolute imports by manipulating sys.path.
"""

from __future__ import annotations

def _resolve_main():
    try:  # Preferred: package context
        from .window_capture import main  # type: ignore
        return main
    except Exception:  # Executed as plain script -> add parent to sys.path
        import os, sys
        here = os.path.abspath(os.path.dirname(__file__))
        parent = os.path.dirname(here)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        from screen_capture.window_capture import main  # type: ignore
        return main


def _run():  # pragma: no cover
    _resolve_main()()


if __name__ == "__main__":  # pragma: no cover
    _run()
