import sys
import os

# Bare imports (e.g. `import gearMath`) work because the module dir is in sys.path.
_mod_dir = os.path.dirname(__file__)
if _mod_dir not in sys.path:
    sys.path.insert(0, _mod_dir)
