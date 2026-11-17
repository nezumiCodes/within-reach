"""Within Reach pipeline: turns public data into static lookup bundles. Public data only."""

import sys


def main() -> None:
    from within_reach_pipeline import cli

    sys.exit(cli.run(sys.argv[1:]))
