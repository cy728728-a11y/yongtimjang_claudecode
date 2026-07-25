# 50-resources

> **외부 자료 및 첨부 파일.** 다운로드한 PDF, 이미지, 참고 링크 등.

## 구조

```
50-resources/
├── attachments/  # 모든 비텍스트 파일 (PDF, 이미지, 영상 등)
└── ...
```

## 첨부파일 명명

```
[관련노트]_[설명].[확장자]

예:
customer-interview_slides.pdf
2026-04-workshop_notes.png
```

관련 노트가 명확하면 prefix로 연결. 그래야 나중에 `grep`으로 찾기 쉬움.

## vs 30-knowledge

- **50-resources**: 원본 파일 저장소 (PDF, 이미지 등 raw)
- **30-knowledge**: 원본에서 추출한 지식/요약 (텍스트)

PDF를 다운로드했으면 → 50-resources에 저장 → 요약을 30-knowledge/00-wiki에 정리.
