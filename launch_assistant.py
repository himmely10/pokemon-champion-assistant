"""Launch the Qt desktop app; optional first argument is an input screenshot."""
import sys


def main():
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
