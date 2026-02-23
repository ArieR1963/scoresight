#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS_DIR = REPO_ROOT / "translations"
DEFAULT_XLSX = TRANSLATIONS_DIR / "scoresight_translations.xlsx"

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


@dataclass
class TsFileInfo:
    path: Path
    file_lang: str
    ts_lang: str


def normalize_text(text: str | None) -> str:
    if text is None:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_cell_ref(cell_ref: str) -> tuple[int, int]:
    m = re.match(r"^([A-Z]+)(\d+)$", cell_ref)
    if not m:
        return 1, 1
    letters, row = m.group(1), int(m.group(2))
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - 64)
    return col, row


def read_cell_value(c: ET.Element, shared_strings: list[str]) -> str:
    t = c.attrib.get("t", "")

    if t == "inlineStr":
        t_node = c.find(f"{{{MAIN_NS}}}is/{{{MAIN_NS}}}t")
        return normalize_text(t_node.text if t_node is not None else "")

    if t == "s":
        v = c.find(f"{{{MAIN_NS}}}v")
        if v is None or v.text is None:
            return ""
        idx = int(v.text)
        return shared_strings[idx] if 0 <= idx < len(shared_strings) else ""

    v = c.find(f"{{{MAIN_NS}}}v")
    return normalize_text(v.text if v is not None else "")


def read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        data = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(data)
    out: list[str] = []
    for si in root.findall(f"{{{MAIN_NS}}}si"):
        parts: list[str] = []
        for t in si.findall(f".//{{{MAIN_NS}}}t"):
            parts.append(normalize_text(t.text))
        out.append("".join(parts))
    return out


def read_xlsx_sheets(xlsx_path: Path) -> dict[str, list[list[str]]]:
    with zipfile.ZipFile(xlsx_path, "r") as zf:
        shared_strings = read_shared_strings(zf)

        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        wb_rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))

        rel_by_id: dict[str, str] = {}
        for rel in wb_rels.findall(f"{{{PKG_REL_NS}}}Relationship"):
            rid = rel.attrib.get("Id", "")
            target = rel.attrib.get("Target", "")
            if rid:
                rel_by_id[rid] = target

        sheets: dict[str, list[list[str]]] = {}
        for sheet in workbook.findall(f"{{{MAIN_NS}}}sheets/{{{MAIN_NS}}}sheet"):
            name = sheet.attrib.get("name", "")
            rid = sheet.attrib.get(f"{{{REL_NS}}}id", "")
            target = rel_by_id.get(rid)
            if not target:
                continue
            sheet_path = "xl/" + target.lstrip("/")
            ws = ET.fromstring(zf.read(sheet_path))

            row_map: dict[int, dict[int, str]] = {}
            max_col = 0
            for row in ws.findall(f"{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row"):
                row_idx = int(row.attrib.get("r", "1"))
                row_cells: dict[int, str] = {}
                for c in row.findall(f"{{{MAIN_NS}}}c"):
                    ref = c.attrib.get("r", "A1")
                    col_idx, _ = split_cell_ref(ref)
                    row_cells[col_idx] = read_cell_value(c, shared_strings)
                    max_col = max(max_col, col_idx)
                row_map[row_idx] = row_cells

            rows: list[list[str]] = []
            if row_map:
                for r in range(1, max(row_map.keys()) + 1):
                    cells = row_map.get(r, {})
                    rows.append([cells.get(c, "") for c in range(1, max_col + 1)])
            sheets[name] = rows

        return sheets


def discover_ts_files() -> list[TsFileInfo]:
    out: list[TsFileInfo] = []
    for ts_path in sorted(TRANSLATIONS_DIR.glob("scoresight_*.ts")):
        file_lang = ts_path.stem.replace("scoresight_", "")
        try:
            root = ET.parse(ts_path).getroot()
            ts_lang = root.attrib.get("language", file_lang)
        except Exception:
            ts_lang = file_lang
        out.append(TsFileInfo(path=ts_path, file_lang=file_lang, ts_lang=ts_lang))
    return out


def alias_lang(lang: str) -> set[str]:
    aliases = {lang}
    # Common mismatch seen in some files/sheets.
    if lang == "ja_JP":
        aliases.add("jp_JP")
    if lang == "jp_JP":
        aliases.add("ja_JP")
    return aliases


def map_ts_langs(ts_files: list[TsFileInfo]) -> dict[str, Path]:
    mapped: dict[str, Path] = {}
    for info in ts_files:
        for key in alias_lang(info.file_lang) | alias_lang(info.ts_lang):
            mapped.setdefault(key, info.path)
    return mapped


def parse_sheet_rows(rows: list[list[str]]) -> dict[str, tuple[str, str]]:
    # Expect header: Key, Context, English (Source), <lang> (Translation), Status
    # Keep only key -> (translation, status)
    out: dict[str, tuple[str, str]] = {}
    if not rows:
        return out
    for row in rows[1:]:
        if len(row) < 5:
            continue
        key = normalize_text(row[0])
        translation = normalize_text(row[3])
        status = normalize_text(row[4]).lower()
        if not key:
            continue
        out[key] = (translation, status)
    return out


def update_ts_file(ts_path: Path, updates: dict[str, tuple[str, str]], apply: bool) -> tuple[int, int]:
    tree = ET.parse(ts_path)
    root = tree.getroot()

    changed = 0
    total = 0
    seen_keys: set[str] = set()
    contexts: dict[str, ET.Element] = {}

    for ctx in root.findall("context"):
        ctx_name = normalize_text(ctx.findtext("name"))
        contexts[ctx_name] = ctx
        for msg in ctx.findall("message"):
            source = normalize_text(msg.findtext("source"))
            key = f"{ctx_name}::{source}"
            if key not in updates:
                continue

            seen_keys.add(key)
            total += 1
            new_text, status = updates[key]
            trans_el = msg.find("translation")
            if trans_el is None:
                trans_el = ET.SubElement(msg, "translation")

            old_text = normalize_text(trans_el.text)
            old_type = trans_el.attrib.get("type", "")

            is_unfinished = (status == "unfinished") or (new_text == "")
            if is_unfinished:
                trans_el.attrib["type"] = "unfinished"
            else:
                trans_el.attrib.pop("type", None)

            trans_el.text = new_text

            if old_text != new_text or old_type != trans_el.attrib.get("type", ""):
                changed += 1

    # Add keys missing from the target TS file (common when source language gained new messages).
    for key, (new_text, status) in updates.items():
        if key in seen_keys:
            continue
        if "::" not in key:
            continue
        ctx_name, source = key.split("::", 1)
        ctx_el = contexts.get(ctx_name)
        if ctx_el is None:
            ctx_el = ET.SubElement(root, "context")
            name_el = ET.SubElement(ctx_el, "name")
            name_el.text = ctx_name
            contexts[ctx_name] = ctx_el

        msg_el = ET.SubElement(ctx_el, "message")
        source_el = ET.SubElement(msg_el, "source")
        source_el.text = source
        trans_el = ET.SubElement(msg_el, "translation")
        trans_el.text = new_text
        is_unfinished = (status == "unfinished") or (new_text == "")
        if is_unfinished:
            trans_el.attrib["type"] = "unfinished"
        changed += 1
        total += 1

    if apply and changed > 0:
        tree.write(ts_path, encoding="utf-8", xml_declaration=True)

    return changed, total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import translations from scoresight_translations.xlsx back into TS files"
    )
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX, help="Path to xlsx")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes to TS files (default: dry-run)",
    )
    args = parser.parse_args()

    if not args.xlsx.exists():
        raise SystemExit(f"XLSX not found: {args.xlsx}")

    sheets = read_xlsx_sheets(args.xlsx)
    ts_files = discover_ts_files()
    lang_to_ts = map_ts_langs(ts_files)

    total_changed = 0
    total_seen = 0
    updated_files = 0

    for sheet_name, rows in sheets.items():
        if sheet_name == "Base_EN":
            continue
        ts_path = lang_to_ts.get(sheet_name)
        if ts_path is None:
            print(f"[skip] No TS file mapped for sheet '{sheet_name}'")
            continue

        updates = parse_sheet_rows(rows)
        changed, seen = update_ts_file(ts_path, updates, apply=args.apply)
        total_changed += changed
        total_seen += seen
        if changed > 0:
            updated_files += 1
        mode = "applied" if args.apply else "dry-run"
        print(f"[{mode}] {ts_path.name}: {changed} changed / {seen} matched")

    print(
        f"Done. files_changed={updated_files}, strings_changed={total_changed}, matched_strings={total_seen}, apply={args.apply}"
    )


if __name__ == "__main__":
    main()
