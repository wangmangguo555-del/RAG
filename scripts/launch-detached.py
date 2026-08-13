"""Launch a Windows process without inheriting the caller's console or pipe handles."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 6:
        raise SystemExit(
            "usage: launch-detached.py <cwd> <stdout> <stderr> <executable> [arguments...]"
        )

    working_directory = Path(sys.argv[1]).resolve()
    stdout_path = Path(sys.argv[2]).resolve()
    stderr_path = Path(sys.argv[3]).resolve()
    command = sys.argv[4:]
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)

    creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    with (
        stdout_path.open("ab", buffering=0) as stdout,
        stderr_path.open("ab", buffering=0) as stderr,
    ):
        process = subprocess.Popen(
            command,
            cwd=working_directory,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
            creationflags=creation_flags,
        )
    print(process.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
