from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.main import app

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPOSITORY_ROOT / 'web' / 'lib' / 'api' / 'openapi.json'


def export_openapi(output: Path = DEFAULT_OUTPUT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(app.openapi(), indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )


def main() -> None:
    parser = argparse.ArgumentParser(description='Export the FastAPI OpenAPI document.')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    export_openapi(arguments.output)


if __name__ == '__main__':
    main()
