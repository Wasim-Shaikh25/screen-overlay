"""Entry point for running the overlay CLI without installation.

Examples:
    python main.py config --api-key sk-...
    python main.py run
    python main.py info
"""

from __future__ import annotations

import sys

from overlay.cli import main

if __name__ == "__main__":
    sys.exit(main())
