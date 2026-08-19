# 테스트가 상위 폴더의 gws_client 등을 import할 수 있게 경로 추가
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
