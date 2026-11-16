"""leveldb .ldb 읽기 최소판 — 크롬 localStorage 가 snappy 로 압축돼 토큰이 정규식에 안 걸리는 문제(2026-11-17) 대응."""
def _varint(b, i):
    r = s = 0
    while True:
        x = b[i]; i += 1
        r |= (x & 0x7f) << s; s += 7
        if x < 0x80: return r, i

def snappy_decompress(b):
    n, i = _varint(b, 0); out = bytearray()
    while i < len(b):
        t = b[i]; i += 1; k = t & 3
        if k == 0:
            ln = t >> 2
            if ln >= 60:
                nb = ln - 59; ln = int.from_bytes(b[i:i+nb], 'little'); i += nb
            ln += 1; out += b[i:i+ln]; i += ln; continue
        if k == 1:
            ln = ((t >> 2) & 7) + 4; off = ((t >> 5) << 8) | b[i]; i += 1
        elif k == 2:
            ln = (t >> 2) + 1; off = int.from_bytes(b[i:i+2], 'little'); i += 2
        else:
            ln = (t >> 2) + 1; off = int.from_bytes(b[i:i+4], 'little'); i += 4
        for _ in range(ln): out.append(out[-off])
    return bytes(out)

def ldb_blocks(data):
    """leveldb .ldb 의 데이터 블록들을 (압축 풀어) 돌려준다."""
    foot = data[-48:]; i = 0
    _, i = _varint(foot, i); _, i = _varint(foot, i)
    ioff, i = _varint(foot, i); isz, i = _varint(foot, i)
    def block(off, sz):
        raw = data[off:off+sz]
        return snappy_decompress(raw) if data[off+sz] == 1 else raw
    idx = block(ioff, isz)
    nres = int.from_bytes(idx[-4:], 'little'); end = len(idx) - 4 - 4*nres
    j = 0; last = b''
    while j < end:
        sh, j = _varint(idx, j); ns, j = _varint(idx, j); vl, j = _varint(idx, j)
        j += ns; v = idx[j:j+vl]; j += vl
        off, p = _varint(v, 0); sz, p = _varint(v, p)
        yield block(off, sz)
