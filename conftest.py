# conftest.py — MOBIUS_MMV プロジェクトルートに置く
# pytest が src/ を module として認識できるようにする
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
