"""Entry point: python -m scada_web [--config path/to/config.yaml]"""

import argparse
import logging
import logging.handlers
import socket
from pathlib import Path

import uvicorn

from .config import load_config
from .server import create_app

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            LOG_DIR / "scada_web.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
        ),
    ],
)


def main():
    parser = argparse.ArgumentParser(description="scada_web — SCADA DDS→Web gateway")
    parser.add_argument(
        "--config", "-c",
        default=str(Path(__file__).parent / "config.yaml"),
        help="Path to YAML config (default: scada_web/config.yaml)",
    )
    parser.add_argument("--host", default=None, help="Override server host")
    parser.add_argument("--port", type=int, default=None, help="Override server port")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.host:
        config.server.host = args.host
    if args.port:
        config.server.port = args.port

    app = create_app(config)

    host = config.server.host
    port = config.server.port
    if host == "0.0.0.0":
        display_host = socket.gethostbyname(socket.gethostname())
    else:
        display_host = host
    print(f"\n  GUI → http://{display_host}:{port}/\n")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
