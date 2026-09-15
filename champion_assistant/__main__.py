import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--web':
        from .webapp import main as web_main
        return web_main(sys.argv[2:])
    from .ui.app import main as desktop_main
    return desktop_main()

if __name__ == "__main__":
    raise SystemExit(main())
