"""Launch the Qt desktop app; optional first argument is an input screenshot."""
import importlib
import os
from pathlib import Path
import sys


def executable_mode(executable=None, *, frozen=None, argv=None):
    """Use the single-window shell unless a web-server CLI was requested."""
    executable = Path(executable or sys.executable)
    frozen = bool(getattr(sys, 'frozen', False) if frozen is None else frozen)
    argv = list(sys.argv[1:] if argv is None else argv)
    server_flags = {'--port', '--no-browser', '--static-root'}
    has_server_flag = any(
        argument in server_flags
        or any(argument.startswith(flag + '=') for flag in server_flags)
        for argument in argv
    )
    return 'web' if frozen and executable.stem.casefold() == 'championlabweb' \
        and has_server_flag else 'desktop'


def prepare_frozen_qt(executable=None, *, frozen=None, loader=None):
    """Load Qt from the onedir bundle without changing caller-relative paths."""
    frozen = bool(getattr(sys, 'frozen', False) if frozen is None else frozen)
    if not frozen:
        return
    previous = Path.cwd()
    try:
        os.chdir(Path(executable or sys.executable).resolve().parent)
        (loader or importlib.import_module)('PySide6.QtCore')
    finally:
        os.chdir(previous)


def main():
    prepare_frozen_qt()
    if len(sys.argv) > 1 and sys.argv[1] == '--web':
        from champion_assistant.webapp import main as web_main
        return web_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == '--self-check':
        from champion_assistant.diagnostics import main as diagnostic_main
        return diagnostic_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == '--update-worker':
        from champion_assistant.update_worker import main as update_main
        return update_main(sys.argv[2:])
    if executable_mode(argv=sys.argv[1:]) == 'web':
        from champion_assistant.webapp import main as web_main
        return web_main(sys.argv[1:])
    from champion_assistant.ui.app import main as gui_main
    return gui_main()

if __name__ == "__main__":
    raise SystemExit(main())
