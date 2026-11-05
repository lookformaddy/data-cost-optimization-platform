#!/usr/bin/env python3
"""Convenience entry point: python scripts/demo.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcop.demo import main

if __name__ == "__main__":
    raise SystemExit(main())
