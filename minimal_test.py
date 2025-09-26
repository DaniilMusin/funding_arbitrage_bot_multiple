#!/usr/bin/env python3
import sys
import os

print("Testing basic Python functionality...")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")

try:
    print("Testing imports...")
    import structlog
    print("✓ structlog imported")

    import appdirs
    print("✓ appdirs imported")

    import logging
    print("✓ logging imported")

    print("✓ All basic imports successful!")
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()