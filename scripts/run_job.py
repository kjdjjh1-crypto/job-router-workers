from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    outdir = Path("jr-artifacts")
    outdir.mkdir(parents=True, exist_ok=True)
    command = json.loads(os.environ.get("JR_COMMAND_JSON", "[]"))
    if not isinstance(command, list) or not command:
        (outdir / "result.json").write_text(
            json.dumps({"ok": False, "error": "empty command"}, indent=2),
            encoding="utf-8",
        )
        return 2
    proc = subprocess.run(command, capture_output=True, text=True)
    (outdir / "stdout.log").write_text(proc.stdout or "", encoding="utf-8")
    (outdir / "stderr.log").write_text(proc.stderr or "", encoding="utf-8")
    (outdir / "result.json").write_text(
        json.dumps(
            {
                "ok": proc.returncode == 0,
                "exit_code": proc.returncode,
                "job_id": os.environ.get("JR_JOB_ID"),
                "shard_index": os.environ.get("JR_SHARD_INDEX"),
                "shard_count": os.environ.get("JR_SHARD_COUNT"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
