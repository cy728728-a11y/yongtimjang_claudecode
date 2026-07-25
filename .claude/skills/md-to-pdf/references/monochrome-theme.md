# Monochrome Dark Theme

> 미니멀 블랙/화이트 핸드아웃 테마. 브랜드 중립적, 범용 문서용.
> Helvetica Neue + Pretendard 폰트 스택.

---

## Font Loading

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" />
```

---

## CSS Variables

```css
:root {
  --color-bg: #FFFFFF;
  --color-bg-dark: #111111;
  --color-bg-muted: #F5F5F5;
  --color-text: #111111;
  --color-text-light: #FFFFFF;
  --color-text-muted: #666666;
  --color-border: #E0E0E0;
  --color-accent: #111111;
  --font-sans: 'Helvetica Neue', 'Pretendard', -apple-system, sans-serif;
  --font-mono: 'SF Mono', 'Menlo', monospace;
}
```

---

## Base Styles

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
@page { size: A4; margin: 0; }
body {
  font-family: var(--font-sans);
  color: var(--color-text);
  background: #888;
  line-height: 1.6;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}
```

---

## Page Container

```css
.page {
  width: 210mm; height: 297mm;
  padding: 18mm 20mm 20mm 20mm;
  margin: 10px auto;
  background: var(--color-bg);
  position: relative; overflow: hidden;
  page-break-after: always; page-break-inside: avoid;
}
@media print {
  body { background: white; }
  .page { margin: 0; box-shadow: none; }
}
@media screen { .page { box-shadow: 0 4px 20px rgba(0,0,0,0.2); } }
```

---

## Cover Page

```css
.cover {
  width: 210mm; height: 297mm;
  background: var(--color-bg-dark); color: var(--color-text-light);
  display: flex; flex-direction: column; justify-content: center;
  padding: 24mm; margin: 10px auto;
  position: relative; overflow: hidden;
  page-break-after: always;
}
@media screen { .cover { box-shadow: 0 4px 20px rgba(0,0,0,0.2); } }
@media print { .cover { margin: 0; box-shadow: none; } }
.cover-label {
  font-family: var(--font-mono); font-size: 8pt;
  letter-spacing: 0.3em; text-transform: uppercase; opacity: 0.4; margin-bottom: 12mm;
}
.cover-title {
  font-family: var(--font-sans); font-size: 28pt; font-weight: 700;
  line-height: 1.15; margin-bottom: 5mm; letter-spacing: -0.02em;
}
.cover-title em { font-style: normal; font-weight: 300; }
.cover-subtitle {
  font-family: var(--font-sans); font-size: 12pt; font-weight: 300;
  opacity: 0.7; margin-bottom: 18mm; line-height: 1.5;
}
.cover-meta {
  display: grid; grid-template-columns: auto 1fr;
  gap: 2mm 6mm; font-size: 8.5pt; opacity: 0.5;
}
.cover-meta dt { font-family: var(--font-mono); font-size: 7.5pt; letter-spacing: 0.05em; text-transform: uppercase; }
.cover-meta dd { margin: 0; }
.cover-brand { position: absolute; bottom: 18mm; left: 24mm; font-size: 10pt; font-weight: 600; letter-spacing: 0.05em; }
```

---

## Page Header / Footer

```css
.page-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10mm; padding-bottom: 3mm;
  border-bottom: 1pt solid var(--color-border);
}
.page-brand { font-size: 8pt; font-weight: 600; opacity: 0.3; letter-spacing: 0.1em; }
.page-number { font-family: var(--font-mono); font-size: 7pt; letter-spacing: 0.1em; opacity: 0.3; }
.page-footer {
  position: absolute; bottom: 12mm; left: 20mm; right: 20mm;
  display: flex; justify-content: space-between;
  font-size: 6.5pt; opacity: 0.25; font-family: var(--font-mono);
}
```

---

## Typography

```css
.section-number { font-family: var(--font-mono); font-size: 6.5pt; letter-spacing: 0.2em; text-transform: uppercase; color: var(--color-text-muted); margin-bottom: 1.5mm; }
.section-title { font-family: var(--font-sans); font-size: 16pt; font-weight: 700; line-height: 1.25; margin-bottom: 6mm; color: var(--color-text); letter-spacing: -0.01em; }
.section-title em { font-weight: 300; font-style: normal; }
h3 { font-family: var(--font-sans); font-size: 8.5pt; font-weight: 700; margin-bottom: 2.5mm; margin-top: 5mm; color: var(--color-text); }
h3:first-of-type { margin-top: 0; }
p { font-size: 8pt; line-height: 1.65; margin-bottom: 2.5mm; color: var(--color-text-muted); }
```

---

## Quotes

```css
.quote {
  background: var(--color-bg-dark); color: var(--color-text-light);
  padding: 4.5mm 5.5mm 4.5mm 5.5mm; border-radius: 1pt; margin: 4mm 0;
}
.quote p { color: var(--color-text-light); margin: 0; font-size: 8pt; line-height: 1.6; }
.quote strong { color: var(--color-text-light); }
.quote code { color: rgba(255,255,255,0.6); background: rgba(255,255,255,0.1); padding: 0.5mm 1.5mm; border-radius: 1pt; }
.quote-light { background: var(--color-bg-muted); color: var(--color-text); border-left: 2pt solid var(--color-text); padding: 3mm 4mm; margin: 3mm 0; font-size: 8pt; line-height: 1.6; }
.quote-light p { color: var(--color-text-muted); margin: 0; }
```

---

## Lists

```css
ul, ol { padding-left: 5mm; margin-bottom: 3mm; }
li { font-size: 8pt; line-height: 1.65; margin-bottom: 1mm; color: var(--color-text-muted); }
li strong { color: var(--color-text); font-weight: 600; }
.flow { counter-reset: flow-counter; list-style: none; padding: 0; }
.flow li { counter-increment: flow-counter; padding-left: 9mm; position: relative; margin-bottom: 2mm; }
.flow li::before { content: counter(flow-counter); position: absolute; left: 0; top: 0.5mm; width: 5mm; height: 5mm; background: var(--color-bg-dark); color: var(--color-text-light); font-family: var(--font-mono); font-size: 6pt; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
.principles { list-style: none; padding: 0; counter-reset: principle; }
.principles li { counter-increment: principle; padding: 2.5mm 0; border-bottom: 0.5pt solid var(--color-border); display: flex; align-items: baseline; gap: 3mm; font-size: 8pt; }
.principles li:last-child { border-bottom: none; }
.principles li::before { content: '0' counter(principle); font-family: var(--font-mono); font-size: 7pt; color: var(--color-text-muted); flex-shrink: 0; width: 6mm; }
```

---

## Cards & Grids

```css
.card-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 3mm; margin: 4mm 0; }
.card-grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 3mm; margin: 4mm 0; }
.card { background: var(--color-bg-muted); border: 0.5pt solid var(--color-border); padding: 4mm; border-radius: 1pt; }
.card-number { font-family: var(--font-mono); font-size: 6pt; letter-spacing: 0.1em; color: var(--color-text-muted); margin-bottom: 1.5mm; }
.card h4 { font-size: 8pt; font-weight: 600; margin-bottom: 1.5mm; }
.card p { font-size: 7.5pt; line-height: 1.55; margin: 0; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 6mm; margin: 3mm 0; }
```

---

## Special Blocks

```css
.dark-inline { background: var(--color-bg-dark); color: var(--color-text-light); margin: 4mm 0; padding: 5mm; border-radius: 1pt; }
.dark-inline h3, .dark-inline h4 { color: var(--color-text-light); }
.dark-inline p { color: rgba(255,255,255,0.75); }
.dark-inline li { color: rgba(255,255,255,0.75); }
.dark-inline li strong { color: var(--color-text-light); }
.dark-inline code { color: rgba(255,255,255,0.6); background: rgba(255,255,255,0.1); padding: 0.5mm 1.5mm; border-radius: 1pt; }
.highlight-box { border: 1.5pt solid var(--color-text); padding: 4mm 5mm; margin: 4mm 0; border-radius: 1pt; }
.highlight-box h4 { font-size: 9pt; font-weight: 700; margin-bottom: 2.5mm; }
.steps { background: var(--color-bg-dark); color: var(--color-text-light); padding: 5mm 6mm; border-radius: 1pt; margin: 3mm 0; }
.steps h4 { font-size: 9pt; font-weight: 600; margin-bottom: 3mm; color: var(--color-text-light); }
.steps ol { counter-reset: step; list-style: none; padding: 0; }
.steps ol li { counter-increment: step; padding: 1.5mm 0 1.5mm 8mm; position: relative; color: rgba(255,255,255,0.8); border-bottom: 0.5pt solid rgba(255,255,255,0.06); font-size: 7.5pt; }
.steps ol li:last-child { border-bottom: none; }
.steps ol li::before { content: counter(step); position: absolute; left: 0; font-family: var(--font-mono); font-size: 7pt; color: rgba(255,255,255,0.5); }
.steps li strong { color: var(--color-text-light); }
.steps li code, .steps code { color: rgba(255,255,255,0.6); background: rgba(255,255,255,0.1); padding: 0.5mm 1.5mm; border-radius: 1pt; }
```

---

## Table

```css
table { width: 100%; border-collapse: collapse; margin: 3mm 0; font-size: 7.5pt; }
th { background: var(--color-bg-dark); color: var(--color-text-light); padding: 2.5mm 3mm; text-align: left; font-weight: 600; font-size: 7pt; letter-spacing: 0.05em; }
td { padding: 2.5mm 3mm; border-bottom: 0.5pt solid var(--color-border); color: var(--color-text-muted); }
tr:last-child td { border-bottom: none; }
```

---

## Utilities

```css
.divider { height: 0.5pt; background: var(--color-border); margin: 5mm 0; }
code { font-family: var(--font-mono); font-size: 7.5pt; color: var(--color-text); background: var(--color-bg-muted); padding: 0.5mm 1.5mm; border-radius: 1pt; }
```

---

## Closing Page

```css
.closing {
  width: 210mm; height: 297mm;
  background: var(--color-bg-dark); color: var(--color-text-light);
  display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center;
  padding: 24mm; margin: 10px auto; page-break-after: avoid;
}
@media screen { .closing { box-shadow: 0 4px 20px rgba(0,0,0,0.2); } }
@media print { .closing { margin: 0; box-shadow: none; } }
.closing-title { font-size: 26pt; font-weight: 700; line-height: 1.2; margin-bottom: 6mm; letter-spacing: -0.02em; }
.closing-title em { font-weight: 300; font-style: normal; }
.closing-sub { font-size: 10pt; opacity: 0.4; margin-bottom: 16mm; }
.closing-info { font-family: var(--font-mono); font-size: 7.5pt; letter-spacing: 0.1em; opacity: 0.3; line-height: 2.2; }
```

---

## Cover HTML Template

```html
<div class="cover">
  <div class="cover-label">{LABEL}</div>
  <h1 class="cover-title">{TITLE}</h1>
  <p class="cover-subtitle">{SUBTITLE}</p>
  <dl class="cover-meta">
    <dt>Date</dt><dd>{DATE}</dd>
    <dt>Author</dt><dd>{AUTHOR}</dd>
  </dl>
  <div class="cover-brand">{BRAND}</div>
</div>
```

## Page HTML Template

```html
<div class="page">
  <div class="page-header">
    <div class="page-brand">{BRAND_SHORT}</div>
    <div class="page-number">{NN} / {TOTAL}</div>
  </div>
  <!-- content here -->
  <div class="page-footer">
    <span>{FOOTER_LEFT}</span>
    <span>{FOOTER_RIGHT}</span>
  </div>
</div>
```
