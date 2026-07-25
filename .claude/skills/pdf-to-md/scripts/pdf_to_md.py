#!/usr/bin/env python3
"""PDF to Markdown converter using pymupdf4llm.

Usage:
  python pdf_to_md.py <pdf_file> [options]

Options:
  --info              Show PDF info only (pages, size, text-vs-scan detection)
  --output PATH       Output .md path (default: <input>_converted.md)
  --pages RANGE       Page range, e.g. "1-5" or "1,3,5-10"
  --images            Extract embedded images to <output>_images/ (linked in markdown)
"""

import argparse
import sys
from pathlib import Path

try:
    import pymupdf4llm
    import pymupdf
except ImportError:
    print(
        "ERROR: pymupdf4llm not installed. Run: pip install pymupdf4llm",
        file=sys.stderr,
    )
    sys.exit(1)


def parse_pages(pages_str: str, total: int) -> list[int]:
    """Parse '1-5,7,9-10' → [0,1,2,3,4,6,8,9] (0-indexed, clamped to total)."""
    result: list[int] = []
    for part in pages_str.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            result.extend(range(int(a) - 1, int(b)))
        else:
            result.append(int(part) - 1)
    return [p for p in result if 0 <= p < total]


def analyze_pdf(path: str) -> dict:
    """Basic inspection: page count, size, text density (detect scan-image PDFs)."""
    doc = pymupdf.open(path)
    total = len(doc)
    size_mb = Path(path).stat().st_size / 1024 / 1024

    sample_pages = min(5, total)
    total_chars = 0
    total_images = 0
    for i in range(sample_pages):
        page = doc[i]
        total_chars += len(page.get_text())
        total_images += len(page.get_images())

    avg_chars = total_chars / sample_pages if sample_pages else 0
    is_likely_scan = avg_chars < 100 and total_images > 0

    doc.close()
    return {
        "pages": total,
        "size_mb": round(size_mb, 2),
        "avg_chars_per_page": round(avg_chars),
        "likely_scan_based": is_likely_scan,
    }


def resolve_output_path(input_path: str, output: str | None) -> Path:
    if output:
        return Path(output)
    p = Path(input_path)
    return p.with_name(f"{p.stem}_converted.md")


def convert(
    path: str,
    output: str | None = None,
    pages: str | None = None,
    extract_images: bool = False,
) -> tuple[Path, dict, int]:
    info = analyze_pdf(path)

    if info["likely_scan_based"]:
        print(
            "WARNING: Looks like a scan-image PDF (very little extractable text per page).",
            file=sys.stderr,
        )
        print(
            "  pymupdf4llm extracts text only — OCR is required for scan PDFs.",
            file=sys.stderr,
        )
        print(
            "  Consider: tesseract, Gemini Vision API, or other OCR tools.",
            file=sys.stderr,
        )

    out_path = resolve_output_path(path, output)
    kwargs: dict = {}

    if pages:
        kwargs["pages"] = parse_pages(pages, info["pages"])

    if extract_images:
        image_dir = out_path.parent / f"{out_path.stem}_images"
        image_dir.mkdir(parents=True, exist_ok=True)
        kwargs["write_images"] = True
        kwargs["image_path"] = str(image_dir)
        kwargs["image_format"] = "png"

    md = pymupdf4llm.to_markdown(path, **kwargs)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    return out_path, info, len(md)


def main() -> None:
    p = argparse.ArgumentParser(description="PDF to Markdown (pymupdf4llm)")
    p.add_argument("pdf", help="PDF file path")
    p.add_argument("--output", help="Output .md path (default: <input>_converted.md)")
    p.add_argument("--pages", help="Page range, e.g. '1-5' or '1,3,5-10'")
    p.add_argument(
        "--images",
        action="store_true",
        help="Extract images to <output>_images/",
    )
    p.add_argument("--info", action="store_true", help="Show PDF info only")
    args = p.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"ERROR: File not found: {args.pdf}", file=sys.stderr)
        sys.exit(1)
    if pdf_path.suffix.lower() != ".pdf":
        print(f"ERROR: Not a PDF file: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    if args.info:
        info = analyze_pdf(args.pdf)
        print(f"PDF:            {args.pdf}")
        print(f"Pages:          {info['pages']}")
        print(f"Size:           {info['size_mb']} MB")
        print(f"Avg chars/page: {info['avg_chars_per_page']} (sample of 5 pages)")
        if info["likely_scan_based"]:
            print("Status:         ⚠️  Likely scan-image — OCR needed for proper extraction")
        else:
            print("Status:         ✓  Text-based, pymupdf4llm conversion should work well")
        return

    out_path, info, md_len = convert(
        args.pdf,
        output=args.output,
        pages=args.pages,
        extract_images=args.images,
    )

    print(f"✓ Converted: {args.pdf} → {out_path}")
    print(f"  Pages: {info['pages']}, Markdown: {md_len:,} chars")
    if args.images:
        print(f"  Images: {out_path.parent / (out_path.stem + '_images')}/")
    if info["likely_scan_based"]:
        print("  ⚠️  Output may be sparse (scan PDF → needs OCR)")


if __name__ == "__main__":
    main()
