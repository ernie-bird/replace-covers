#!/usr/bin/env python3
import argparse
import csv
import json
import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from pypdf import PdfReader, PdfWriter, PageObject, Transformation
from pypdf.errors import PdfReadError


# ===================== Settings =====================

DEFAULT_SETTINGS = {
    "enable_blank_second": True,
    "enable_preserve_insert": True,

    "unimportant_keywords": [
        "©", "(c)", "copyright", "all rights reserved", "unauthorized",
        "reproduction", "permission", "rights reserved"
    ],
    "important_keywords": [
        "table of contents", "contents", "song list", "songlist",
        "orchestration", "instrumentation", "index", "track list", "music list"
    ],

    "max_short_unimportant_chars": 200,
    "max_short_unimportant_lines": 4,
    "important_min_words": 60,
    "important_min_lines": 5,
    "important_long_line_chars": 40
}

def load_settings(settings_path):
    """
    Load JSON settings (defaults to ./settings.json). If missing/invalid, use defaults.
    """
    if settings_path is None:
        candidate = Path("settings.json")
    else:
        candidate = Path(settings_path).expanduser().resolve()

    if not candidate.exists():
        print(f"⚠️  Settings file not found at {candidate}. Using built-in defaults.")
        return DEFAULT_SETTINGS.copy()

    try:
        with open(candidate, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = {**DEFAULT_SETTINGS, **data}
        print(f"✅ Loaded settings from {candidate}")
        return merged
    except Exception as e:
        print(f"⚠️  Failed to read settings file ({candidate}): {e}")
        print("Using built-in defaults.")
        return DEFAULT_SETTINGS.copy()


# ===================== PDF helpers =====================

def points_size(page):
    mb = page.mediabox
    return float(mb.width), float(mb.height)

def build_cover_map(covers_dir: Path, showcode: str):
    """
    Map of basename -> cover path, filtered to stems that start with '<showcode>-'.
    """
    prefix = f"{showcode}-"
    out = {}
    for p in covers_dir.glob("*.pdf"):
        if not p.stem.startswith(prefix):
            continue
        try:
            r = PdfReader(str(p))
            if r.is_encrypted or len(r.pages) < 1:
                continue
            out[p.stem] = p
        except PdfReadError:
            continue
        except Exception:
            continue
    return out

def iter_show_pdfs(show_dir: Path, showcode: str):
    """
    Yield (stem, path) for readable PDFs under show_dir/** with stems that start with '<showcode>-'.
    """
    prefix = f"{showcode}-"
    for p in show_dir.rglob("*.pdf"):
        if not p.stem.startswith(prefix):
            continue
        try:
            r = PdfReader(str(p))
            if not r.is_encrypted:
                yield p.stem, p
        except PdfReadError:
            continue
        except Exception:
            continue

def make_scaled_centered_cover(cover_page, target_w, target_h):
    """
    Return a new page of size (target_w, target_h) with cover_page content scaled
    uniformly to fit and centered (no cropping).
    """
    src_w, src_h = points_size(cover_page)
    if src_w == 0 or src_h == 0:
        return PageObject.create_blank_page(width=target_w, height=target_h)

    scale = min(target_w / src_w, target_h / src_h)
    new_w, new_h = src_w * scale, src_h * scale
    tx = (target_w - new_w) / 2.0
    ty = (target_h - new_h) / 2.0

    out = PageObject.create_blank_page(width=target_w, height=target_h)
    t = Transformation().scale(scale).translate(tx, ty)
    out.merge_transformed_page(cover_page, t)
    return out

def unique_backup_path(global_old_dir: Path, filename: str) -> Path:
    """
    Return a unique backup path in global_old_dir. If name exists, append '_2'
    before extension; keep appending until unique.
    """
    global_old_dir.mkdir(parents=True, exist_ok=True)
    base, ext = os.path.splitext(filename)
    candidate = global_old_dir / f"{base}{ext}"
    while candidate.exists():
        base = f"{base}_2"
        candidate = global_old_dir / f"{base}{ext}"
    return candidate


# ===================== Page-2 decision logic (settings-driven) =====================

def decide_second_page_action(page, settings: dict) -> str:
    """
    Return one of:
      - 'blank'                 : make page 2 blank (drop original page 2)
      - 'preserve_insert_blank' : keep original page 2 and insert a blank before it
      - 'preserve'              : keep original page 2 as-is (no extra blank)

    Precedence:
      • If enable_preserve_insert is TRUE -> apply intelligence:
          - If page looks IMPORTANT -> 'preserve_insert_blank'
          - Else -> 'blank' if enable_blank_second else 'preserve'
      • If enable_preserve_insert is FALSE:
          - If enable_blank_second is TRUE -> 'blank' (unconditional)
          - Else -> 'preserve'
    """
    enable_blank = bool(settings.get("enable_blank_second", True))
    enable_preserve_insert = bool(settings.get("enable_preserve_insert", True))

    if not enable_preserve_insert:
        return "blank" if enable_blank else "preserve"

    # Intelligence path
    try:
        txt = page.extract_text() or ""
    except Exception:
        txt = ""

    clean = txt.strip()
    low = clean.lower()
    words = low.split()
    lines = [ln.strip() for ln in low.splitlines() if ln.strip()]

    important_keywords = settings.get("important_keywords", [])
    if any(k in low for k in important_keywords):
        return "preserve_insert_blank"

    important_by_size = (
        len(words) >= settings.get("important_min_words", 60)
        or (
            len(lines) >= settings.get("important_min_lines", 5)
            and any(len(ln) >= settings.get("important_long_line_chars", 40) for ln in lines)
        )
    )
    if important_by_size:
        return "preserve_insert_blank"

    return "blank" if enable_blank else "preserve"


# ===================== Replace / Write =====================

def replace_file_with_writer(target_pdf: Path, writer: PdfWriter, global_old_dir: Path) -> Path:
    """
    Move original to global OLD, then atomically place writer's content at target path.
    Return backup path.
    """
    backup_path = unique_backup_path(global_old_dir, target_pdf.name)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf", dir=str(target_pdf.parent)) as tmp:
        writer.write(tmp)
        tmp_path = Path(tmp.name)

    try:
        shutil.move(str(target_pdf), str(backup_path))
    except Exception as e:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise RuntimeError(f"Failed to back up original file: {e}")

    os.replace(tmp_path, target_pdf)
    return backup_path


def process_one(target_pdf: Path, cover_pdf: Path, global_old_dir: Path, settings: dict):
    """
    Replace page 1 with cover. Handle page 2 per precedence + settings schema.
    Always ensure output has at least 2 pages (add blank if missing).
    """
    reader_target = PdfReader(str(target_pdf))
    reader_cover = PdfReader(str(cover_pdf))

    # First pages and sizes
    t_first = reader_target.pages[0]
    c_first = reader_cover.pages[0]
    t_w, t_h = points_size(t_first)
    c_w, c_h = points_size(c_first)

    same_size = abs(t_w - c_w) < 0.5 and abs(t_h - c_h) < 0.5
    new_first = c_first if same_size else make_scaled_centered_cover(c_first, t_w, t_h)

    writer = PdfWriter()
    writer.add_page(new_first)

    # Page 2 handling
    has_second = len(reader_target.pages) >= 2
    if has_second:
        orig_second = reader_target.pages[1]
        decision = decide_second_page_action(orig_second, settings)
        second_w, second_h = points_size(orig_second)
    else:
        orig_second = None
        decision = "blank"
        second_w, second_h = t_w, t_h

    blank_second = PageObject.create_blank_page(width=second_w, height=second_h)

    if decision == "blank":
        writer.add_page(blank_second)
        start_idx = 2
    elif decision == "preserve_insert_blank":
        writer.add_page(blank_second)      # new page 2
        if orig_second is not None:
            writer.add_page(orig_second)   # new page 3
        start_idx = 2
    else:  # "preserve"
        if orig_second is not None:
            writer.add_page(orig_second)
        else:
            writer.add_page(blank_second)  # ensure at least 2 pages
        start_idx = 2

    # Append remaining pages (original 3..end)
    for i in range(start_idx, len(reader_target.pages)):
        writer.add_page(reader_target.pages[i])

    # Write and backup
    backup_path = replace_file_with_writer(target_pdf, writer, global_old_dir)

    return {
        "file_path": str(target_pdf),
        "backup_path": str(backup_path),
        "second_page_action": decision,  # 'blank' | 'preserve_insert_blank' | 'preserve'
        "size_changed": (not same_size),
        "target_first_page_size": f"{t_w:.2f}x{t_h:.2f}",
        "cover_first_page_size": f"{c_w:.2f}x{c_h:.2f}",
    }


# ===================== Single-line Progress Bar + Log =====================

def _supports_ansi() -> bool:
    return sys.stdout.isatty()

def _clear_line():
    # Clear current line (ANSI): move to start + erase
    if _supports_ansi():
        sys.stdout.write("\r\x1b[2K")
    else:
        sys.stdout.write("\r")
    sys.stdout.flush()

def print_progress(done: int, total: int, status: str = "", width: int = 40):
    """
    In-place terminal progress bar. No extra lines; redraw as needed.
    """
    total = max(total, 1)
    frac = done / total
    filled = int(width * frac)
    bar = "█" * filled + "-" * (width - filled)
    percent = f"{frac * 100:6.2f}%"
    sys.stdout.write(f"\r🔄 Processing… [{bar}] {percent} ({done:>2}/{total}) {status}")
    sys.stdout.flush()
    if done >= total:
        sys.stdout.write("\n")

def log_and_refresh(msg: str, done: int, total: int, status: str):
    """
    Print a single log line ABOVE the bar without duplicating the bar line.
    """
    _clear_line()
    print(msg)
    print_progress(done, total, status)


# ===================== CLI / Main =====================

def auto_report_path(show_dir: Path, showcode: str):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return show_dir / f"{showcode}_{ts}.csv"

def main():
    parser = argparse.ArgumentParser(
        description="Replace first pages with covers (filtered by showcode). Page-2 behavior controlled by JSON settings."
    )
    parser.add_argument("--covers", required=True, help="Path to the covers folder (mixed shows)")
    parser.add_argument("--root", required=True, help="Root folder that contains per-show folders")
    parser.add_argument("--showcode", required=True, help="Show code (e.g., PROM or ADDA)")
    parser.add_argument("--report", help="Optional path for CSV report")
    parser.add_argument("--settings", help="Path to JSON settings file (default: ./settings.json)")
    args = parser.parse_args()

    settings = load_settings(args.settings if args.settings else None)

    covers_dir = Path(args.covers).expanduser().resolve()
    root_dir = Path(args.root).expanduser().resolve()
    show_dir = (root_dir / args.showcode).resolve()

    if not covers_dir.is_dir():
        print(f"❌ ERROR: Covers directory not found: {covers_dir}")
        sys.exit(1)
    if not root_dir.is_dir():
        print(f"❌ ERROR: Root directory not found: {root_dir}")
        sys.exit(1)
    if not show_dir.is_dir():
        print(f"❌ ERROR: Show folder not found under root: {show_dir}")
        sys.exit(1)

    # Single global OLD folder under the show folder
    global_old_dir = show_dir / "OLD"
    global_old_dir.mkdir(parents=True, exist_ok=True)

    # Build maps (filtered by showcode prefix)
    cover_map = build_cover_map(covers_dir, args.showcode)
    targets = {}
    for name, path in iter_show_pdfs(show_dir, args.showcode):
        targets.setdefault(name, []).append(path)

    # Prepare the list of actual work items (only those with matching covers)
    work_items = []
    for name, paths in targets.items():
        cover = cover_map.get(name)
        if not cover:
            continue
        for p in paths:
            work_items.append((name, p, cover))

    total_to_process = len(work_items)

    # Report path
    report_path = Path(args.report).expanduser().resolve() if args.report else auto_report_path(show_dir, args.showcode)

    print(f"🗂️  Show folder: {show_dir}")
    print(f"🔎 Filtering by showcode: {args.showcode} (prefix '{args.showcode}-')")
    print(f"ℹ️  Covers considered: {len(cover_map)}   Targets considered: {len(targets)}")
    print(f"🧮 Will process (matched): {total_to_process}\n")

    updated_rows = []
    missing_cover_names = [name for name in targets.keys() if name not in cover_map]

    # Kick off progress bar; keep it on one line throughout processing
    done = 0
    print_progress(done, total_to_process)

    for name, target_pdf, cover in work_items:
        try:
            result = process_one(target_pdf, cover, global_old_dir, settings)
            updated_rows.append({"action": "updated", "name": name, **result})

            action_map = {
                "blank": "blanked ⬜",
                "preserve_insert_blank": "preserved + blank inserted ➕⬜",
                "preserve": "preserved 🧾"
            }
            msg = (f"✅ OK: {target_pdf.name} — page 1 replaced; page 2 "
                   f"{action_map.get(result['second_page_action'], '?')} "
                   f"(backup → {global_old_dir})")
            done += 1
            log_and_refresh(msg, done, total_to_process, "✅")
        except Exception as e:
            updated_rows.append({
                "action": "error",
                "name": name,
                "file_path": str(target_pdf),
                "backup_path": "",
                "error": str(e),
            })
            msg = f"❌ ERR: {target_pdf.name} — {e}"
            done += 1
            log_and_refresh(msg, done, total_to_process, "❌")

    # Covers present but no target with that name (info only)
    missing_in_book = set(cover_map.keys()) - set(targets.keys())

    # Add missing lines to CSV
    for nm in sorted(set(missing_cover_names)):
        updated_rows.append({
            "action": "no_cover_for_book_file",
            "name": nm,
            "file_path": ";".join(str(p) for p in targets.get(nm, [])),
            "backup_path": "",
        })
    for nm in sorted(missing_in_book):
        updated_rows.append({
            "action": "no_book_file_for_cover",
            "name": nm,
            "file_path": str(cover_map[nm]),
            "backup_path": "",
        })

    # Write CSV
    fieldnames = [
        "action",
        "name",
        "file_path",
        "backup_path",
        "second_page_action",
        "size_changed",
        "target_first_page_size",
        "cover_first_page_size",
        "error",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in updated_rows:
            for key in fieldnames:
                row.setdefault(key, "")
            w.writerow(row)

    # Summary
    print("\n📊 ================ SUMMARY ================\n")
    print(f"ℹ️  Covers considered: {len(cover_map)}")
    print(f"ℹ️  Targets considered: {len(targets)}")
    print(f"✅ Files updated: {sum(1 for r in updated_rows if r['action']=='updated')}")
    print(f"⚠️  Missing covers for: {sum(1 for r in updated_rows if r['action']=='no_cover_for_book_file')}")
    print(f"⚠️  Missing target files for covers: {sum(1 for r in updated_rows if r['action']=='no_book_file_for_cover')}")
    print(f"❌ Errors: {sum(1 for r in updated_rows if r['action']=='error')}")
    print("\n------------------------------------------")
    if missing_cover_names:
        print("⚠️  No cover found for these BOOK files:")
        for nm in sorted(set(missing_cover_names)):
            print(f"   - {nm}")
    if missing_in_book:
        print("\n⚠️  No BOOK file found for these covers:")
        for nm in sorted(missing_in_book):
            print(f"   - {nm}")
    print("\n------------------------------------------")
    print(f"📄 Detailed report written to: {report_path}")
    print("🎉 Done.\n")


if __name__ == "__main__":
    main()
