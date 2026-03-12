#!/usr/bin/env python3
"""
Entry point for Drift Detector.
  python run.py
  # or with uvicorn directly:
  uvicorn dd.app:app --host 0.0.0.0 --port 8899 --reload
"""

import uvicorn
from dd.config import HOST, PORT, HOST_A, HOST_B, DB_DRIVER, DB_PATH

if __name__ == "__main__":
    print(f"Drift Detector starting...")
    print(f"  HOST_A:    {HOST_A}")
    print(f"  HOST_B:    {HOST_B}")
    print(f"  DB_DRIVER: {DB_DRIVER}")
    print(f"  DB_PATH:   {DB_PATH}")
    print(f"  Listen:    {HOST}:{PORT}")
    uvicorn.run("dd.app:app", host=HOST, port=PORT, reload=True)
