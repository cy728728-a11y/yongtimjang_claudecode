# -*- coding: utf-8 -*-
"""`.venv`(CLI venv)로 도는 테스트만 사는 디렉터리.

`webapp/pytest.ini` 의 `norecursedirs` 가 이 디렉터리를 기본 수집에서 뺀다 —
`.venv-web` 에는 `Vision`(pyobjc) 도 `PIL` 도 없는 것이 설계이기 때문이다(D-19).
여기 테스트를 돌리려면 인터프리터와 경로를 **둘 다** 명시해야 한다:

    .venv/bin/python3 -m pytest webapp/tests/cli/test_ocr_determinism.py

`__init__.py` 가 있어야 pytest 가 패키지 조상(`webapp/tests` → `webapp` → 저장소 루트)을
따라 올라가 루트를 `sys.path` 에 넣는다. 그래야 `from webapp import ...` 가 산다.
"""
