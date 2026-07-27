"""Entry point: python -m scada_web [--config path/to/config.yaml]"""

import argparse
import logging
from pathlib import Path

import uvicorn

from .config import load_config
from .server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
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
    uvicorn.run(app, host=config.server.host, port=config.server.port)


if __name__ == "__main__":
    main()
