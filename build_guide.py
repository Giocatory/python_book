"""
Сборка книги «Python: с нуля до Senior» в .docx.

Установка:  pip install python-docx
Запуск:     python build_guide.py
Результат:  Python_Zero_to_Senior.docx
Контент:    все файлы content/*.md, склеиваются по алфавиту (00_, 01_, 02_, ...)

Поддерживаемый Markdown-диалект:
  # / ## / ### / ####   -> заголовки 1-4 уровня (глава / тема / подтема / деталь)
  ```python ... ```     -> блок кода (моноширинный, с фоном)
  - пункт               -> маркированный список (2 пробела = вложенность)
  1. пункт              -> нумерованный список (номер сохраняется как в тексте)
  | a | b |             -> таблица (вторая строка |---|---| обязательна)
  > [!NOTE] текст       -> врезка «Важно»   (также [!WARNING], [!TASK], [!TIP])
  ---                   -> разрыв страницы
  [[TOC]]               -> автособираемое оглавление Word
  **жирный** *курсив* `код`
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

CONTENT_DIR = Path("content")
OUTPUT = Path("Python_Zero_to_Senior.docx")

BODY_FONT, HEAD_FONT, CODE_FONT = "Times New Roman", "Calibri", "Consolas"
ACCENT = "1F3B73"
CODE_BG = "F4F5F7"
CALLOUT = {
    "NOTE": ("EEF3FB", "1F3B73", "Важно."),
    "TIP": ("F1F6EE", "3F6B33", "Совет."),
    "WARNING": ("FDF1E7", "B45309", "Предупреждение."),
    "TASK": ("F3EEF9", "6B3FA0", "Практика."),
}


def _el(tag: str, **attrs):
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn(k), v)
    return e


def shade(pr, fill: str) -> None:
    pr.append(_el("w:shd", **{"w:val": "clear", "w:color": "auto", "w:fill": fill}))


def left_bar(p, color: str):
    pbdr = OxmlElement("w:pBdr")
    pbdr.append(_el("w:left", **{"w:val": "single", "w:sz": "18",
                                 "w:space": "8", "w:color": color}))
    p._p.get_or_add_pPr().append(pbdr)


def field(paragraph, instruction: str, placeholder: str = ""):
    run = paragraph.add_run()
    begin = _el("w:fldChar", **{"w:fldCharType": "begin"})
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    sep = _el("w:fldChar", **{"w:fldCharType": "separate"})
    txt = OxmlElement("w:t")
    txt.text = placeholder
    end = _el("w:fldChar", **{"w:fldCharType": "end"})
    for e in (begin, instr, sep, txt, end):
        run._r.append(e)


def setup_styles(doc: Document) -> None:
    st = doc.styles
    normal = st["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(11.5)
    rpr = normal.element.get_or_add_rPr()
    rpr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    rpr.append(_el("w:lang", **{"w:val": "ru-RU"}))
    pf = normal.paragraph_format
    pf.space_after, pf.line_spacing = Pt(6), 1.15
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    heads = {"Heading 1": (20, 0, 18), "Heading 2": (15, 16, 8),
             "Heading 3": (12.5, 12, 6), "Heading 4": (11.5, 10, 4)}
    for name, (size, before, after) in heads.items():
        s = st[name]
        s.font.name, s.font.size = HEAD_FONT, Pt(size)
        s.font.bold, s.font.italic = True, name == "Heading 4"
        s.font.color.rgb = RGBColor.from_string(ACCENT)
        p = s.paragraph_format
        p.space_before, p.space_after = Pt(before), Pt(after)
        p.keep_with_next = True
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        if name == "Heading 1":
            p.page_break_before = True

    code = st.add_style("Guide Code", WD_STYLE_TYPE.PARAGRAPH)
    code.base_style = st["Normal"]
    code.font.name, code.font.size = CODE_FONT, Pt(9.5)
    cp = code.paragraph_format
    cp.alignment = WD_ALIGN_PARAGRAPH.LEFT
    cp.line_spacing, cp.space_before, cp.space_after = 1.0, Pt(6), Pt(8)
    cp.left_indent, cp.right_indent = Cm(0.4), Cm(0.2)
    cp.keep_together = True

    for i, indent in enumerate((0.7, 1.3, 1.9), start=1):
        s = st.add_style(f"Guide L{i}", WD_STYLE_TYPE.PARAGRAPH)
        s.base_style = st["Normal"]
        p = s.paragraph_format
        p.left_indent, p.first_line_indent = Cm(indent), Cm(-0.45)
        p.space_after, p.alignment = Pt(3), WD_ALIGN_PARAGRAPH.LEFT

    call = st.add_style("Guide Callout", WD_STYLE_TYPE.PARAGRAPH)
    call.base_style = st["Normal"]
    call.font.size = Pt(10.5)
    p = call.paragraph_format
    p.left_indent, p.right_indent = Cm(0.3), Cm(0.2)
    p.space_before, p.space_after = Pt(8), Pt(8)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT


def setup_section(doc: Document) -> None:
    s = doc.sections[0]
    s.page_width, s.page_height = Cm(21), Cm(29.7)
    s.left_margin, s.right_margin = Cm(2.5), Cm(1.5)
    s.top_margin, s.bottom_margin = Cm(2), Cm(2)
    s.different_first_page_header_footer = True

    h = s.header.paragraphs[0]
    h.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = h.add_run("Python: с нуля до Senior")
    r.font.size, r.font.name = Pt(9), HEAD_FONT
    r.font.color.rgb = RGBColor(0x80, 0x80, 0x80)

    f = s.footer.paragraphs[0]
    f.alignment = WD_ALIGN_PARAGRAPH.CENTER
    field(f, "PAGE", "1")
    f.runs[0].font.size = Pt(10)


def title_page(doc: Document) -> None:
    for _ in range(4):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("PYTHON")
    r.font.name, r.font.size, r.font.bold = HEAD_FONT, Pt(46), True
    r.font.color.rgb = RGBColor.from_string(ACCENT)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("С НУЛЯ ДО SENIOR")
    r.font.name, r.font.size, r.font.bold = HEAD_FONT, Pt(24), True

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Пошаговое руководство backend-инженера")
    r.font.size, r.font.italic = Pt(14), True

    for _ in range(2):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("64 главы · 12 частей · от установки интерпретатора\n"
              "до архитектуры высоконагруженных систем").font.size = Pt(12)
    for _ in range(6):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("Python 3.12+ · FastAPI · SQLAlchemy 2.0 · PostgreSQL · Docker").font.size = Pt(11)
    doc.add_page_break()


def add_toc(doc: Document) -> None:
    h = doc.add_paragraph("ОГЛАВЛЕНИЕ")
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h.runs[0].font.name = HEAD_FONT
    h.runs[0].font.size = Pt(20)
    h.runs[0].font.bold = True
    h.runs[0].font.color.rgb = RGBColor.from_string(ACCENT)
    p = doc.add_paragraph()
    field(p, r'TOC \o "1-3" \h \z \u',
          "Оглавление соберётся автоматически. Если пусто: Ctrl+A, затем F9.")
    doc.add_page_break()


INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\*[^*\n]+?\*)", re.S)


def add_inline(p, text: str) -> None:
    for tok in INLINE.split(text):
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**") and len(tok) > 4:
            p.add_run(tok[2:-2]).bold = True
        elif tok.startswith("`") and tok.endswith("`") and len(tok) > 2:
            r = p.add_run(tok[1:-1])
            r.font.name, r.font.size = CODE_FONT, Pt(10)
        elif tok.startswith("*") and tok.endswith("*") and len(tok) > 2:
            p.add_run(tok[1:-1]).italic = True
        else:
            p.add_run(tok)


def add_code(doc: Document, lines: list[str]) -> None:
    p = doc.add_paragraph(style="Guide Code")
    p.add_run("\n".join(lines))
    shade(p._p.get_or_add_pPr(), CODE_BG)


def add_callout(doc: Document, kind: str, text: str) -> None:
    bg, bar, label = CALLOUT.get(kind, CALLOUT["NOTE"])
    p = doc.add_paragraph(style="Guide Callout")
    p.add_run(label + " ").bold = True
    add_inline(p, text)
    shade(p._p.get_or_add_pPr(), bg)
    left_bar(p, bar)


def add_table(doc: Document, rows: list[list[str]]) -> None:
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    for i, row in enumerate(rows):
        for j, cell_text in enumerate(row):
            cell = t.cell(i, j)
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
            add_inline(p, cell_text)
            for r in p.runs:
                r.font.size = Pt(10)
                if i == 0:
                    r.bold = True
            if i == 0:
                shade(cell._tc.get_or_add_tcPr(), "E8EDF5")
    doc.add_paragraph()


def render(doc: Document, md: str) -> None:
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            block, i = [], i + 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            add_code(doc, block)
            i += 1
            continue

        if stripped.startswith("|"):
            raw = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw.append(lines[i].strip())
                i += 1
            rows = [[c.strip() for c in r.strip("|").split("|")]
                    for r in raw if not re.fullmatch(r"\|[\s:\-|]+\|", r)]
            if rows:
                add_table(doc, rows)
            continue

        if stripped.startswith("> "):
            body, i = [], i
            while i < len(lines) and lines[i].strip().startswith(">"):
                body.append(lines[i].strip().lstrip(">").strip())
                i += 1
            text = " ".join(body)
            m = re.match(r"\[!(\w+)\]\s*(.*)", text, re.S)
            kind, text = (m.group(1), m.group(2)) if m else ("NOTE", text)
            add_callout(doc, kind, text)
            continue

        if stripped == "[[TOC]]":
            add_toc(doc)
        elif stripped == "---":
            doc.add_page_break()
        elif m := re.match(r"^(#{1,4})\s+(.*)$", stripped):
            doc.add_heading(m.group(2).strip(), level=len(m.group(1)))
        elif m := re.match(r"^(\s*)[-*]\s+(.*)$", line):
            level = min(len(m.group(1)) // 2 + 1, 3)
            p = doc.add_paragraph(style=f"Guide L{level}")
            p.add_run("•\t" if level == 1 else "◦\t")
            add_inline(p, m.group(2))
        elif m := re.match(r"^(\s*)(\d+[.)])\s+(.*)$", line):
            level = min(len(m.group(1)) // 2 + 1, 3)
            p = doc.add_paragraph(style=f"Guide L{level}")
            p.add_run(m.group(2) + "\t")
            add_inline(p, m.group(3))
        elif stripped:
            add_inline(doc.add_paragraph(), stripped)
        i += 1


def main() -> None:
    doc = Document()
    setup_styles(doc)
    setup_section(doc)
    doc.core_properties.title = "Python: с нуля до Senior"
    doc.core_properties.subject = "Пошаговое руководство backend-инженера"
    doc.core_properties.language = "ru-RU"
    doc.settings.element.append(_el("w:updateFields", **{"w:val": "true"}))

    title_page(doc)
    files = sorted(CONTENT_DIR.glob("*.md"))
    if not files:
        raise SystemExit("Положите md-файлы в папку content/")
    for f in files:
        render(doc, f.read_text(encoding="utf-8"))
        print(f"  + {f.name}")
    doc.save(OUTPUT)
    print(f"\nГотово: {OUTPUT.resolve()}")


if __name__ == "__main__":
    main()