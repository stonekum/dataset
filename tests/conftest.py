"""pytest 共享 fixtures。让 tests 能直接 import utils.*。"""

import sys
from pathlib import Path

# 加项目根到 sys.path，避免 tests 目录里跑测试找不到 utils
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
