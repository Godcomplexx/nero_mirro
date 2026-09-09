# Runtime package for realtime rPPG pipeline.
import sys
from pathlib import Path

_root = str(Path(__file__).parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)
