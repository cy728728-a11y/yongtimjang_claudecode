#!/usr/bin/env python3
"""`.env` 로더 1벌 — 기존 3벌(sellha · sellerlife common · cookie_extractor) 통합.

KEY=VALUE 라인 파서. 따옴표(' ")와 주석(#)·빈 줄을 무시하고,
환경변수가 이미 있으면 그쪽을 우선한다(prefer_environ).
"""
import os


def load_env(env_path, keys=None, prefer_environ=True):
    """env_path 를 파싱해 dict 반환.

    keys: 뽑을 키 목록(iterable). 주면 그 키만, None 이면 파일의 전 키.
    prefer_environ: True 면 os.environ 에 이미 있는 값이 파일값을 이긴다.
    파일이 없거나 못 읽으면 빈(또는 환경변수만 채운) dict.
    """
    wanted = set(keys) if keys is not None else None
    cfg = {}
    if wanted is not None and prefer_environ:
        for k in wanted:
            v = os.environ.get(k)
            if v:
                cfg[k] = v

    if os.path.exists(env_path):
        try:
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if wanted is not None and k not in wanted:
                        continue
                    if prefer_environ and cfg.get(k):
                        continue  # 환경변수 우선 — 파일값으로 덮지 않음
                    cfg[k] = v
        except OSError as e:
            print(f"[경고] .env 읽기 실패: {e}")

    if wanted is not None and not prefer_environ:
        # 파일에 없던 키는 환경변수로 보충
        for k in wanted:
            if not cfg.get(k):
                v = os.environ.get(k)
                if v:
                    cfg[k] = v
    return cfg
