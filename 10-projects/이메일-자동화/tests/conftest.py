# 테스트가 상위 폴더의 gws_client 등을 import할 수 있게 경로 추가
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def _block_real_subprocess_calls(monkeypatch):
    """모든 테스트에 기본 적용되는 안전장치.

    subprocess.run을 기본적으로 막아서, 특정 gws_client 함수(trash_message 등)를
    patch하지 않은 테스트가 실수로 실제 gws CLI/Gmail 계정을 건드리는 사고를 방지한다.
    개별 테스트가 monkeypatch.setattr(subprocess, "run", fake_run)로 명시적으로 재정의하면
    같은 monkeypatch 인스턴스 안에서 나중 호출이 이전 값을 덮어쓰므로 그 쪽이 우선 적용된다.
    """
    def _blocked_run(*args, **kwargs):
        raise AssertionError(
            "subprocess.run이 패치되지 않은 채 호출됨 — 실제 gws CLI/Gmail 호출을 막기 위한 안전장치. "
            "테스트에서 monkeypatch.setattr(subprocess, 'run', fake_run) 등으로 명시적으로 패치하세요."
        )

    monkeypatch.setattr(subprocess, "run", _blocked_run)
