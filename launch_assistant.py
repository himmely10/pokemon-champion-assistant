"""Launch the Qt desktop app; optional first argument is an input screenshot."""
from pathlib import Path
import sys


def executable_mode(executable=None, *, frozen=None):
    """Select the installed entry point without relying on shortcut arguments."""
    executable = Path(executable or sys.executable)
    frozen = bool(getattr(sys, 'frozen', False) if frozen is None else frozen)
    return 'web' if frozen and executable.stem.casefold() == 'championlabweb' else 'desktop'


def main():
    if executable_mode() == 'web':
        from champion_assistant.webapp import main as web_main
        return web_main(sys.argv[1:])
    if len(sys.argv) > 1 and sys.argv[1] == '--web':
        from champion_assistant.webapp import main as web_main
        return web_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == '--self-check':
        from champion_assistant.diagnostics import main as diagnostic_main
        return diagnostic_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == '--update-worker':
        from champion_assistant.update_worker import main as update_main
        return update_main(sys.argv[2:])
    from champion_assistant.ui.app import main as gui_main
    return gui_main()

if __name__ == "__main__":
    raise SystemExit(main())
