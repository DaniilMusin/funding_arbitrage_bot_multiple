import os
import subprocess
import sys

from setuptools import find_packages, setup

def main():
    version = "1.0.0"
    
    # Find packages for our custom modules only
    packages = find_packages(include=["strategies", "strategies.*", "adapters", "adapters.*", "services", "services.*"])
    
    package_data = {
        "strategies": ["funding_arbitrage/*.py"],
        "adapters": ["core_ext/*.py"],
        "services": ["controllers/**/*.py"],
    }
    
    install_requires = [
        # Core Hummingbot dependencies
        "aiohttp>=3.8.5",
        "asyncssh>=2.13.2", 
        "aioprocessing>=2.0.1",
        "aioresponses>=0.7.4",
        "aiounittest>=1.4.2",
        "async-timeout>=4.0.2,<5",
        "bidict>=0.22.1",
        "bip-utils",
        "cachetools>=5.3.1",
        "commlib-py>=0.11",
        "cryptography>=41.0.2",
        "eth-account>=0.13.0",
        "injective-py",
        "msgpack-python",
        "numpy>=1.25.0,<2",
        "objgraph",
        "pandas>=2.0.3",
        "pandas-ta>=0.3.14b",
        "prompt_toolkit>=3.0.39",
        "protobuf>=4.23.3",
        "psutil>=5.9.5",
        "pydantic>=2",
        "pyjwt>=2.3.0",
        "pyperclip>=1.8.2",
        "requests>=2.31.0",
        "ruamel.yaml>=0.2.5",
        "safe-pysha3",
        "scalecodec",
        "scipy>=1.11.1",
        "six>=1.16.0",
        "sqlalchemy>=1.4.49",
        "tabulate>=0.9.0",
        "ujson>=5.7.0",
        "urllib3>=1.26.15,<2.0",
        "redis>=5.0.0",
        "web3",
        "xrpl-py>=4.1.0",
        "PyYAML>=0.2.5",
        # Additional dependencies for custom extensions
        "structlog",
        "asyncpg",
    ]

    if "DEV_MODE" in os.environ:
        version += ".dev1"

    setup(
        name="funding-arbitrage-bot",
        version=version,
        description="Funding Rate Arbitrage Bot - Custom strategies and extensions for Hummingbot",
        url="https://github.com/your-org/funding-arbitrage-bot",
        author="Your Organization",
        author_email="dev@your-org.com",
        license="Apache 2.0",
        packages=packages,
        package_data=package_data,
        install_requires=install_requires,
        python_requires=">=3.10",
        scripts=[
            "bin/hummingbot_quickstart.py"
        ],
        entry_points={
            "console_scripts": [
                "funding-arb-bot=scripts.start:main",
            ],
        },
    )


if __name__ == "__main__":
    main()