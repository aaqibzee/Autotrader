"""Load the bundled vehicle taxonomy (Feature 02 §1). Runs on every deploy.

    uv run python -m scripts.load_taxonomy [--data-dir PATH]

Idempotent: a second run reports zero inserts and updates. Prints the LoadReport as one
JSON log line; exits non-zero, having written nothing, if the data is invalid.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

import structlog

from app.core.telemetry import configure_logging
from app.db.session import SyncSessionLocal
from app.modules.taxonomy.dataset import DEFAULT_DATA_DIR, read_taxonomy
from app.modules.taxonomy.services import SlugChangeError, TaxonomyDataError, load_taxonomy

logger = structlog.get_logger('scripts.load_taxonomy')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Load the vehicle taxonomy CSVs.')
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA_DIR)
    arguments = parser.parse_args(argv)

    configure_logging()
    try:
        data = read_taxonomy(arguments.data_dir)
        with SyncSessionLocal.begin() as session:
            report = load_taxonomy(session, data)
    except TaxonomyDataError as error:
        logger.error('taxonomy_load_rejected', problems=error.problems)
        return 1
    except SlugChangeError as error:
        logger.error('taxonomy_load_rejected', problems=[str(error)])
        return 1

    logger.info('taxonomy_loaded', **asdict(report))
    return 0


if __name__ == '__main__':
    sys.exit(main())
