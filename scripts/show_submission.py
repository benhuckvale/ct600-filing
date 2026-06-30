#!/usr/bin/env python3
"""Print a readable summary of a recorded submission attempt.

Usage:
    python scripts/show_submission.py [attempt-dir]   # default: latest

With no argument, summarises the most recent submissions/<stamp>-<target>/.
Shows the outcome and, for a rejection, the list of HMRC ChRIS errors.
"""
import sys

from submission_lib import resolve_dir, summarize


def main() -> None:
    summarize(resolve_dir(sys.argv[1] if len(sys.argv) > 1 else None))


if __name__ == "__main__":
    main()
