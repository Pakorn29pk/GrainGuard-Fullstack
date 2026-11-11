"""Start both sites locally with a fresh synthetic database each time."""
import argparse
import asyncio
import os
from pathlib import Path
import tempfile

from run_review import make_review, serve
from grainguard_hub.auth import AuthStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-port", type=int, default=8886)
    parser.add_argument("--online-port", type=int, default=8887)
    args = parser.parse_args()
    os.environ.pop("GG_PUBLIC_ORIGIN", None)
    with tempfile.TemporaryDirectory(prefix="grainguard-preview-", ignore_cleanup_errors=True) as directory:
        auth = AuthStore(directory)
        auth.provision_site_owner("pumpkintec", "pumpkintec", "PumpkinTec", "pumpkintec")
        auth.provision_site_owner("uengliangseng", "uengliangseng", "โรงสีไฟอึ้งเลี่ยงเส็ง", "uengliangseng")
        runtime, app = make_review(Path(directory))
        try:
            print(f"Local:  http://127.0.0.1:{args.local_port}/login/local.html", flush=True)
            print(f"Online: http://127.0.0.1:{args.online_port}/login/online.html", flush=True)
            print("Preview accounts: pumpkintec and uengliangseng. Password matches the username.", flush=True)
            asyncio.run(serve(app, args.local_port, args.online_port))
        finally:
            runtime.stop()


if __name__ == "__main__":
    main()
