"""Entry point so `python -m bagbot` works as an alias for `python -m bagbot.cli`."""
from .cli import main
import sys
sys.exit(main())
