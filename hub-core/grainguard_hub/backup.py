"""Online backup of the SQLite database:  python -m grainguard_hub.backup [dest_dir] [keep]

Uses the SQLite backup API (consistent snapshot while the hub is running)."""
from __future__ import annotations

import os
import sqlite3
import sys
import time

from .config import load_config


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cfg = load_config()
    dest = argv[0] if argv else os.path.join(cfg.data_dir, "backup")
    keep = int(argv[1]) if len(argv) > 1 else 14
    os.makedirs(dest, exist_ok=True)
    out = os.path.join(dest, "grainguard-%s.db" % time.strftime("%Y%m%d-%H%M%S"))
    src = sqlite3.connect("file:%s?mode=ro" % cfg.db(), uri=True, timeout=30)
    dst = sqlite3.connect(out)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    files = sorted(f for f in os.listdir(dest) if f.startswith("grainguard-") and f.endswith(".db"))
    for f in files[:-keep]:
        os.remove(os.path.join(dest, f))
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
