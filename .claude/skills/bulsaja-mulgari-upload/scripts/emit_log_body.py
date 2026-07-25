# -*- coding: utf-8 -*-
# 물갈이 재업로드 로그 append용 body JSON 생성.
# 사용: python emit_log_body.py <targets_tsv> <batch_idx> <taskId> <group_name> <YYYY-MM-DD>
# targets_tsv: 각 줄 "productId\t상품명" (배치순 정렬, 20개씩 한 배치)
# 출력: {"values":[[...최대 20행...]]}  ← ensure_ascii=True(기본)로 한글을 \uXXXX로 인코딩(커맨드라인 깨짐 방지)
import sys, json

try:
    tsv = sys.argv[1]
    idx = int(sys.argv[2])
    taskId = sys.argv[3]
    group = sys.argv[4]
    date = sys.argv[5]
    B = 20  # 배치당 상품 수 (market_upload 최대치)

    rows = [l.rstrip("\n") for l in open(tsv, encoding="utf-8") if l.strip()]
    seg = rows[(idx - 1) * B:(idx - 1) * B + B]  # 해당 배치 구간

    values = []
    for line in seg:
        p = line.split("\t")
        pid = p[0]
        name = p[1] if len(p) > 1 else ""
        # 컬럼(A~K): 작업일시·마켓그룹·상품명·판매자상품코드·taskId·배치#·접수결과·최종결과·결과확인일시·비고·productId
        # 삭제 로그와 같은 탭을 쓰므로 비고="재업로드"로 구분
        values.append([date, group, name, "", taskId, str(idx), "접수됨", "", "", "재업로드", pid])

    # ensure_ascii=True(기본): 한글이 \uXXXX ASCII로 나가 커맨드라인/코드페이지에서 안 깨짐
    print(json.dumps({"values": values}))
except Exception as e:
    # 실패 시 에러를 stderr로 (호출측이 감지)
    sys.stderr.write("emit_log_body error: %s\n" % e)
    sys.exit(1)
