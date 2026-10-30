"""Entry point for Streamlit Cloud — loads the unified AAOP app."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.app import *  # noqa: F401, F403
