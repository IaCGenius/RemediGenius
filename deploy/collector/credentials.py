"""SDK credential_process for workstation exports; never a Hermes tool."""
import json
from pathlib import Path

if __name__ == '__main__':
    print(Path('/run/operator/credentials.json').read_text())
