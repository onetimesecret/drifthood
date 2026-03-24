#!/usr/bin/env python3

# drift-detector/run.py

"""
Entry point for Drift Detector.

Server mode (default):
  python run.py
  # or with uvicorn directly:
  uvicorn dd.app:app --host 0.0.0.0 --port 8899 --reload

CLI mode:
  python run.py compare --spec api.yaml --host-a http://localhost:8000 --host-b http://localhost:8001
"""

import sys
import uvicorn

# CLI subcommands that delegate to dd.cli
CLI_COMMANDS = {"compare"}


def start_server():
    """Start the uvicorn server."""
    from dd.config import DB_DRIVER, DB_PATH, HOST, HOST_A, HOST_B, PORT

    print("Drift Detector starting...")
    print(f"  HOST_A:    {HOST_A}")
    print(f"  HOST_B:    {HOST_B}")
    print(f"  DB_DRIVER: {DB_DRIVER}")
    print(f"  DB_PATH:   {DB_PATH}")
    print(f"  Listen:    {HOST}:{PORT}")
    uvicorn.run("dd.app:app", host=HOST, port=PORT, reload=True)


if __name__ == "__main__":
    # Check if first arg is a CLI command
    if len(sys.argv) > 1 and sys.argv[1] in CLI_COMMANDS:
        from dd.cli import main
        main()
    else:
        start_server()
