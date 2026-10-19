from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = ROOT / 'backend' / 'app'
ALLOWED_FILE = Path('core/jobs.py')
FORBIDDEN_METHODS = {'delay', 'apply_async'}


def main() -> int:
    violations: list[str] = []
    for path in APP_ROOT.rglob('*.py'):
        relative_path = path.relative_to(APP_ROOT)
        if relative_path == ALLOWED_FILE:
            continue
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        except SyntaxError as error:
            violations.append(f'{path}:{error.lineno}: unable to parse Python source: {error.msg}')
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in FORBIDDEN_METHODS
            ):
                method = node.func.attr
                violations.append(f'{path}:{node.lineno}: direct Celery .{method}() is forbidden')

    if violations:
        print('\n'.join(violations))
        return 1
    print('No direct Celery .delay() or .apply_async() calls found outside core/jobs.py.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
