"""Future Pi entry point. Run ONLY after user acceptance and deployment review."""
import argparse
import asyncio
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'hub-core'))
from grainguard_hub.app import Hub, setup_logging
from grainguard_hub.sites import SiteRuntime,close_hub
from grainguard_hub.config import load_config
from grainguard_hub.listeners import serve

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--config')
    p.add_argument('--local-port',type=int,default=8080)
    p.add_argument('--online-port',type=int,default=8081)
    args=p.parse_args()
    setup_logging()
    cfg=load_config(args.config)
    cfg.dashboard_path=str(ROOT/'dashboard/index.html')
    # Both listeners loopback only. Public HTTPS must target the ONLINE port.
    hub=Hub(cfg,http_enabled=False)
    runtime=None
    try:
        runtime=SiteRuntime(hub)
        runtime.start()
        asyncio.run(serve(runtime.app,args.local_port,args.online_port))
    finally:
        if runtime is not None:
            runtime.stop()
        else:
            close_hub(hub)

if __name__=='__main__': main()
