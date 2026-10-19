from __future__ import annotations

import json
import secrets
import string
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    fake_key = 'AKIA' + ''.join(
        secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16)
    )

    with tempfile.TemporaryDirectory(prefix='autotrader-gitleaks-') as temporary_directory:
        temporary_root = Path(temporary_directory)
        source = temporary_root / 'source'
        source.mkdir()
        (source / 'fake-cloud-credential.txt').write_text(
            f'AWS_ACCESS_KEY_ID={fake_key}\n',
            encoding='utf-8',
        )
        report_path = temporary_root / 'report.json'
        try:
            result = subprocess.run(
                [
                    'gitleaks',
                    'detect',
                    '--no-git',
                    '--source',
                    str(source),
                    '--report-format',
                    'json',
                    '--report-path',
                    str(report_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            print('Gitleaks executable is not installed in this environment.')
            return 2
        if not report_path.exists():
            print(result.stderr)
            print('Gitleaks did not produce a report for the synthetic fixture.')
            return 1
        try:
            findings = json.loads(report_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            print('Gitleaks produced an invalid JSON report.')
            return 1

    if result.returncode == 0 or not findings:
        print('Gitleaks did not detect the generated fake AWS access key.')
        return 1
    print('Gitleaks detects generated AWS access-key patterns.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
