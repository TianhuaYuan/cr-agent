"""评测脚本 CLI 入口（Phase 10: Task 10.2）。

用法：
  python scripts/eval.py --limit 5
  python -m backend.services.evaluation.eval --all
"""
import sys
from pathlib import Path

# 把项目根加入 sys.path，使 `python scripts/eval.py` 能 import backend
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.evaluation.eval import main

if __name__ == "__main__":
    main()
