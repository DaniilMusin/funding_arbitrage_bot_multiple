#!/usr/bin/env python3
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("Testing basic imports...")
    import structlog
    print("structlog imported successfully")

    import appdirs
    print("appdirs imported successfully")

    print("Testing hummingbot imports...")
    import hummingbot.core_ext.logging_conf
    print("logging_conf imported successfully")

    import hummingbot
    print("hummingbot imported successfully")

    print("All imports successful!")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()