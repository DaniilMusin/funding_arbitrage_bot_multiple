import os
import subprocess
import sys
import fnmatch

import numpy as np
from setuptools import find_packages, setup

is_posix = (os.name == "posix")

if is_posix:
    os_name = subprocess.check_output("uname").decode("utf8")
    if "Darwin" in os_name:
        os.environ["CFLAGS"] = "-stdlib=libc++ -std=c++11"
    else:
        os.environ["CFLAGS"] = "-std=c++11"

if os.environ.get("WITHOUT_CYTHON_OPTIMIZATIONS"):
    os.environ["CFLAGS"] += " -O0"


def main():
    cpu_count = os.cpu_count() or 8
    version = "20250612"
    all_packages = find_packages(include=["hummingbot", "hummingbot.*"], )
    excluded_paths = [
        "hummingbot.connector.gateway.clob_spot.data_sources.injective",
        "hummingbot.connector.gateway.clob_perp.data_sources.injective_perpetual"
    ]
    packages = [pkg for pkg in all_packages if not any(fnmatch.fnmatch(pkg, pattern) for pattern in excluded_paths)]
    package_data = {
        "hummingbot": [
            "core/cpp/*",
            "VERSION",
            "templates/*TEMPLATE.yml"
        ],
    }
    install_requires = [
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
    ]

    if "DEV_MODE" in os.environ:
        version += ".dev1"
        package_data[""] = [
            "*.pxd", "*.pyx", "*.h"
        ]
        package_data["hummingbot"].append("core/cpp/*.cpp")

    setup(name="hummingbot",
          version=version,
          description="Hummingbot",
          url="https://github.com/hummingbot/hummingbot",
          author="Hummingbot Foundation",
          author_email="dev@hummingbot.org",
          license="Apache 2.0",
          packages=packages,
          package_data=package_data,
          install_requires=install_requires,
          include_dirs=[
              np.get_include()
          ],
          scripts=[
              "bin/hummingbot_quickstart.py"
          ],
          )


if __name__ == "__main__":
    main()