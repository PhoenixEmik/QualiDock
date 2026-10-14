import argparse
import os
import uvicorn
from .app import create_app
from .config import Settings


def main():
    parser = argparse.ArgumentParser(description="Start a single-user QualiDock session")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    os.umask(0o077)
    settings = Settings.from_env()
    if "QUALIDOCK_TOKEN" not in os.environ:
        print(f"Open http://{args.host}:{args.port}{settings.prefix}/#token={settings.token}", flush=True)
    else:
        print(f"QualiDock listening on {args.host}:{args.port}{settings.prefix}/", flush=True)
    uvicorn.run(create_app(settings), host=args.host, port=args.port, proxy_headers=False, timeout_graceful_shutdown=15)


if __name__ == "__main__":
    main()
