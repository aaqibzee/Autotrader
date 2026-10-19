from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
IMPORTER = BACKEND / 'app' / 'modules' / 'listings' / '_contract_probe.py'
TARGET = BACKEND / 'app' / 'modules' / 'leads' / 'models.py'


def main() -> int:
    if IMPORTER.exists() or TARGET.exists():
        raise SystemExit('Refusing to overwrite an existing import-boundary fixture.')

    IMPORTER.write_text(
        'from app.modules.leads.models import Lead\n',
        encoding='utf-8',
    )
    TARGET.write_text('class Lead: ...\n', encoding='utf-8')
    try:
        result = subprocess.run(
            ['uv', 'run', 'lint-imports', '--no-cache', '--no-logo'],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        IMPORTER.unlink(missing_ok=True)
        TARGET.unlink(missing_ok=True)

    if result.returncode == 0:
        print('Import-linter accepted a forbidden cross-domain model import.')
        return 1
    output = result.stdout + result.stderr
    if 'app.modules.leads.models' not in output:
        print(output)
        print('Import-linter failed, but not for the expected module boundary.')
        return 1
    print('Import-linter rejects cross-domain model imports.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
