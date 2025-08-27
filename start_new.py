#!/usr/bin/env python3

"""
Funding Arbitrage Bot Startup Script

This script initializes the bot with the new modular architecture:
- Hummingbot core as submodule
- Custom strategies as plugins
- Core extensions as adapters
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project directories to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "hummingbot-upstream"))
sys.path.insert(0, str(project_root / "strategies"))
sys.path.insert(0, str(project_root / "adapters"))
sys.path.insert(0, str(project_root / "services"))

# Import custom modules
from adapters.core_ext.logging_conf import setup as setup_logging
from adapters.core_ext.state_sync import sync_loop

# Import Hummingbot modules
from hummingbot.client.hummingbot_application import HummingbotApplication
from hummingbot.core.utils.async_utils import safe_ensure_future


async def main():
    """Main entry point for the funding arbitrage bot."""
    
    # Set up structured logging
    setup_logging()
    
    print("🚀 Starting Funding Arbitrage Bot...")
    print(f"📁 Project root: {project_root}")
    print(f"📦 Hummingbot submodule: {project_root / 'hummingbot-upstream'}")
    
    # Verify that the submodule is properly initialized
    hummingbot_path = project_root / "hummingbot-upstream" / "hummingbot"
    if not hummingbot_path.exists():
        print("❌ Error: Hummingbot submodule not found!")
        print("   Run './install.sh' to set up the project properly")
        sys.exit(1)
    
    # Start the state sync service if enabled
    if os.getenv("ENABLE_STATE_SYNC", "false").lower() == "true":
        print("🔄 Starting state synchronization service...")
        safe_ensure_future(sync_loop())
    
    # Initialize and start the Hummingbot application
    print("🤖 Starting Hummingbot application...")
    
    # Set configuration paths
    os.environ.setdefault("CONFIG_FILE_PATH", str(project_root / "conf"))
    os.environ.setdefault("LOGS_PATH", str(project_root / "logs"))
    os.environ.setdefault("DATA_PATH", str(project_root / "data"))
    
    # Start the application
    app = HummingbotApplication.main_application()
    
    if app is not None:
        await app.main_async()
    else:
        print("❌ Failed to initialize Hummingbot application")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())