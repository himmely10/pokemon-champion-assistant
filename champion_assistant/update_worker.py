"""One background entry point, usable from Python and the frozen application."""
import argparse
import json
from pathlib import Path

from .data.usage import update_usage
from .data.update_service import UpdateService


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--operation', choices=['check', 'sync', 'validate', 'rollback', 'import'])
    parser.add_argument('--channel', default='')
    parser.add_argument('--hours', type=int, choices=[0, 24, 72, 168], default=24)
    parser.add_argument('--package', type=Path)
    parser.add_argument('--if-due', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.operation:
            if args.root is None:
                parser.error('--operation 必须提供 --root')
            service = UpdateService(args.root, args.channel)
            if args.operation in {'sync', 'check'}:
                result = getattr(service, args.operation)(if_due=args.if_due, hours=args.hours)
            elif args.operation == 'import':
                if args.package is None:
                    parser.error('导入必须提供 --package')
                result = service.install(args.package)
            else:
                result = getattr(service, args.operation)()
        else:
            if args.data_dir is None:
                parser.error('必须提供资料目录')
            result = update_usage(args.data_dir, due_hours=24 if args.if_due else None)
        # Portable through frozen Windows pipes regardless of console code page.
        print(json.dumps(result, ensure_ascii=True))
        return 2 if result['status'] == 'partial' else 0
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else '网络或本地文件操作失败，请重试。'
        print(json.dumps({'status': 'failed', 'message': message + ' 原资料已保留。'}, ensure_ascii=True))
        return 1
