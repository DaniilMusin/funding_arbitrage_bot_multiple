import os
import runpy
import sys


def main() -> None:
    repo_root = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(repo_root, 'hb-check')

    if os.path.exists(script_path):
        # Execute the existing Click CLI script
        runpy.run_path(script_path, run_name='__main__')
        return

    print('hb-check script not found in installation. Please ensure the package was installed with scripts enabled.')
    sys.exit(1)

