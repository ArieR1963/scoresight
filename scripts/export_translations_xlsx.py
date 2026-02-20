#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS_DIR = REPO_ROOT / "translations"
OUT_XLSX = TRANSLATIONS_DIR / "scoresight_translations.xlsx"


@dataclass
class Entry:
    key: str
    context: str
    source: str
    translation: str
    status: str


def normalize_text(text: str | None) -> str:
    if text is None:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def parse_ts(path: Path):
    tree = ET.parse(path)
    root = tree.getroot()
    lang = root.attrib.get("language", path.stem.replace("scoresight_", ""))

    entries: list[Entry] = []
    for ctx in root.findall("context"):
        ctx_name = normalize_text(ctx.findtext("name"))
        for msg in ctx.findall("message"):
            source = normalize_text(msg.findtext("source"))
            trans_el = msg.find("translation")
            translation = normalize_text(trans_el.text if trans_el is not None else "")
            status = "translated"
            if trans_el is None:
                status = "missing"
            elif trans_el.attrib.get("type") == "unfinished":
                status = "unfinished"
            key = f"{ctx_name}::{source}"
            entries.append(Entry(key, ctx_name, source, translation, status))
    return lang, entries


def col_name(idx: int) -> str:
    s = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


def inline_cell(ref: str, value: str) -> str:
    # Preserve whitespace/newlines with xml:space="preserve"
    return (
        f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">'
        f"{escape(value)}"
        "</t></is></c>"
    )


def worksheet_xml(rows: list[list[str]]) -> str:
    xml_rows: list[str] = []
    for r_idx, row in enumerate(rows, start=1):
        cells: list[str] = []
        for c_idx, value in enumerate(row, start=1):
            ref = f"{col_name(c_idx)}{r_idx}"
            cells.append(inline_cell(ref, value))
        xml_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        f'{"".join(xml_rows)}'
        "</sheetData>"
        "</worksheet>"
    )


def safe_sheet_name(name: str) -> str:
    name = re.sub(r"[\\/*?:\[\]]", "_", name)
    return name[:31] or "Sheet"


def build_xlsx(ts_files: list[Path], out_path: Path) -> None:
    parsed: dict[str, list[Entry]] = {}
    for ts in ts_files:
        lang, entries = parse_ts(ts)
        parsed[lang] = entries

    if "en_US" not in parsed:
        raise RuntimeError("Missing translations/scoresight_en_US.ts")

    en_entries = parsed["en_US"]
    en_by_key = {e.key: e for e in en_entries}
    key_order = [e.key for e in en_entries]

    sheets: list[tuple[str, list[list[str]]]] = []

    # Base sheet
    base_rows = [["Key", "Context", "English (Source)"]]
    for k in key_order:
        e = en_by_key[k]
        base_rows.append([e.key, e.context, e.source])
    sheets.append(("Base_EN", base_rows))

    # One tab per language with English + translation side by side
    for lang in sorted(parsed.keys()):
        if lang == "en_US":
            continue
        by_key = {e.key: e for e in parsed[lang]}
        rows = [["Key", "Context", "English (Source)", f"{lang} (Translation)", "Status"]]
        for k in key_order:
            en = en_by_key[k]
            tr = by_key.get(k)
            rows.append([
                en.key,
                en.context,
                en.source,
                tr.translation if tr else "",
                tr.status if tr else "missing",
            ])
        sheets.append((safe_sheet_name(lang), rows))

    workbook_xml_sheets: list[str] = []
    workbook_rels: list[str] = []
    content_types_overrides: list[str] = []

    for i, (sheet_name, _) in enumerate(sheets, start=1):
        workbook_xml_sheets.append(
            f'<sheet name="{escape(sheet_name)}" sheetId="{i}" r:id="rId{i}"/>'
        )
        workbook_rels.append(
            f'<Relationship Id="rId{i}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i}.xml"/>'
        )
        content_types_overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        f'{"".join(content_types_overrides)}'
        '</Types>'
    )

    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '</Relationships>'
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets>'
        f'{"".join(workbook_xml_sheets)}'
        '</sheets>'
        '</workbook>'
    )

    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{"".join(workbook_rels)}'
        '</Relationships>'
    )

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
        '<cellXfs count="1"><xf xfId="0"/></cellXfs>'
        '</styleSheet>'
    )

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/styles.xml", styles_xml)

        for i, (_, rows) in enumerate(sheets, start=1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", worksheet_xml(rows))


def main() -> None:
    ts_files = sorted(TRANSLATIONS_DIR.glob("scoresight_*.ts"))
    if not ts_files:
        raise RuntimeError("No .ts translation files found")
    build_xlsx(ts_files, OUT_XLSX)
    print(f"Created: {OUT_XLSX}")


if __name__ == "__main__":
    main()
