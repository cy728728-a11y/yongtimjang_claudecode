#!/usr/bin/env python3
"""이중 키 중복 그룹핑 — 코드 정본 층(순수 로직, 네트워크 0).

**왜 union 병합인가**: 불사자 복사본은 코드·상품번호를 둘 다 공유하고 재수집분은
상품번호만 공유한다. 그런데 필드 결측이 있으면(번호 없는 복사본 등) 단일 키로는
같은 상품이 갈라져 **유니크 수가 부풀고 분기 게이트가 편향**된다. 그래서 두 키를
각각 간선으로 보고 union-find 로 묶는다. 대표 키는 번호(tb:) > 코드 > solo 순.
"""
import json
import os


def code_of(rec):
    """레코드 1건의 우선 키(표시·정렬용). 그룹핑 자체는 build_code_map 의 union 이 한다."""
    pno = str(rec.get("타오바오상품번호") or "").strip()
    if pno:
        return f"tb:{pno}"
    code = str(rec.get("불사자코드") or "").strip()
    if code:
        return code
    return f"solo:{rec.get('productId')}"


def build_code_map(recs, membership):
    """{pid: 스냅샷레코드} + {pid: 그룹소속} → {코드: [인스턴스...]}.

    같은 상품번호 **또는** 같은 불사자코드를 공유하면 한 그룹(union) —
    한쪽 필드가 결측인 인스턴스도 다른 키로 이어지면 병합된다.
    """
    parent = {pid: pid for pid in recs}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = {}
    for pid, rec in recs.items():
        pno = str(rec.get("타오바오상품번호") or "").strip()
        code = str(rec.get("불사자코드") or "").strip()
        if pno:
            edges.setdefault(("tb", pno), []).append(pid)
        if code:
            edges.setdefault(("code", code), []).append(pid)
    for pids in edges.values():
        r = find(pids[0])
        for other in pids[1:]:
            parent[find(other)] = r

    groups = {}
    for pid in recs:
        groups.setdefault(find(pid), []).append(pid)

    out = {}
    for members in groups.values():
        key = _canonical_key(members, recs)
        insts = []
        for pid in members:
            m = membership.get(pid) or {}
            insts.append({
                "productId": pid,
                "groupId": m.get("groupId"),
                "그룹명": str(m.get("그룹명") or ""),
                "상태코드": m.get("상태코드"),
                "불사자코드": str(recs[pid].get("불사자코드") or ""),
            })
        insts.sort(key=lambda x: (x["그룹명"], x["productId"]))
        out[key] = insts
    return out


def _canonical_key(members, recs):
    """그룹 대표 키 — 번호 > 코드 > solo. pid 정렬 순회로 결정적."""
    for pid in sorted(members):
        pno = str(recs[pid].get("타오바오상품번호") or "").strip()
        if pno:
            return f"tb:{pno}"
    for pid in sorted(members):
        code = str(recs[pid].get("불사자코드") or "").strip()
        if code:
            return code
    return f"solo:{sorted(members)[0]}"


def same_group_dups(code_map):
    """같은 마켓그룹 안의 중복(중복 노출 위험) — 전파가 아니라 사람 판단 대상.

    반환의 groupId 키는 int(메모리) — JSON 저장·재로드를 거치면 문자열이 된다
    (json.dump 는 dict 키를 항상 str 로 직렬화). 소비 측이 groupId 로 조회할 땐
    str(groupId) 로 맞춰야 한다.
    """
    bad = {}
    for code, insts in code_map.items():
        seen = {}
        for it in insts:
            seen.setdefault(it["groupId"], []).append(it["productId"])
        d = {g: pids for g, pids in seen.items() if len(pids) > 1}
        if d:
            bad[code] = d
    return bad


def choose_representative(insts, done_counts=None):
    """결정적 대표: ①현황판 완료 작업 수 최다 ②그룹명 ③pid. 같은 입력=같은 대표.

    **알려진 공백**(피어리뷰 2026-07-28): `상태코드`(삭제·판매중지 등)를 보지 않는다.
    목록 API가 실제로 그런 값을 주는지, 준다면 어떤 코드인지 확인된 바 없어 지금
    필터를 추측해 넣지 않는다 — Step 0 파일럿(1그룹)에서 상태코드 분포를 먼저 보고
    필요하면 이 정렬 키 맨 앞에 "정상 여부"를 추가한다.
    """
    dc = done_counts or {}
    best = sorted(insts, key=lambda x: (-dc.get(x["productId"], 0),
                                        x["그룹명"], x["productId"]))
    return best[0]["productId"]


def stats_of(code_map):
    sizes = sorted((len(v) for v in code_map.values()), reverse=True)
    hist = {}
    for n in sizes:
        hist[n] = hist.get(n, 0) + 1
    return {
        "인스턴스수": sum(sizes),
        "유니크수": len(sizes),
        "solo수": sum(1 for c in code_map if c.startswith("solo:")),
        "최대복사본수": sizes[0] if sizes else 0,
        "복사본수_분포": hist,           # {인스턴스수: 코드수}
        "동일그룹중복_코드수": len(same_group_dups(code_map)),
    }


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def shuffle_name(name, keywords, code, group_id, rep_group_id=None):
    """마켓별 상품명 변형 — 블록 순서만 결정적으로 바꾼다(중복 노출 회피).

    키워드는 불가분 블록: 공백 제거 연속 문자열이 보존돼야 적합도(R5) 만점이 유지된다.
    seed = sha1(code:groupId) — 그룹명이 아니라 groupId(불변 정수)를 쓴다(개명 안전).
    대표가 속한 그룹은 항등(확정명 그대로).
    """
    import hashlib
    import random
    if rep_group_id is not None and group_id == rep_group_id:
        return name
    tokens = name.split()
    used = [False] * len(tokens)
    blocks = []
    # 긴 키워드부터 토큰 연속 구간에 매칭(공백 제거 비교) — 겹치지 않게 잠근다
    for kw in sorted((k for k in keywords if k), key=len, reverse=True):
        flat = kw.replace(" ", "")
        for i in range(len(tokens)):
            if used[i]:
                continue
            acc = ""
            for j in range(i, len(tokens)):
                if used[j]:
                    break
                acc += tokens[j]
                if acc == flat:
                    blocks.append((i, tokens[i:j + 1]))
                    for k in range(i, j + 1):
                        used[k] = True
                    break
                if len(acc) > len(flat):
                    break
            else:
                continue
            if used[i]:
                break
    for i, t in enumerate(tokens):
        if not used[i]:
            blocks.append((i, [t]))
    blocks.sort(key=lambda b: b[0])          # 원 순서 기준으로 정렬한 뒤
    seq = [b[1] for b in blocks]
    seed = int(hashlib.sha1(f"{code}:{group_id}".encode()).hexdigest()[:12], 16)
    random.Random(seed).shuffle(seq)         # 결정적 순열
    return " ".join(t for blk in seq for t in blk)
