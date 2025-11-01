import argparse
import csv
import os
import shutil
from pathlib import Path


def find_latest_report(show_dir: Path, showcode: str) -> Path | None:
    """Return the most recent CSV report matching '<showcode>_*.csv' in show_dir, else None."""
    pattern = f"{showcode}_*.csv"
    candidates = sorted(
        show_dir.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def validate_under(parent: Path, child: Path) -> bool:
    """True if 'child' lives inside 'parent' (after resolving)."""
    try:
        child_res = child.resolve()
        parent_res = parent.resolve()
        return parent_res in child_res.parents or child_res == parent_res
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Restore originals from OLD back to their original locations using the forward-run CSV, then delete OLD (unless --keep-old)."
    )
    parser.add_argument("--root", required=True, help="Path to the root folder containing per-show folders")
    parser.add_argument("--showcode", required=True, help="Show code folder name, e.g., PROM or ADDA")
    parser.add_argument("--report", required=False, help="Explicit CSV report path; if omitted, pick latest <showcode>_*.csv in the show folder")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without changing any files")
    parser.add_argument(
        "--keep-old",
        action="store_true",
        help="Copy back (keep backups in OLD) and DO NOT delete OLD afterwards",
    )
    args = parser.parse_args()

    root_dir = Path(args.root).expanduser().resolve()
    showcode = args.showcode
    show_dir = (root_dir / showcode).resolve()
    if not show_dir.is_dir():
        print(f"ERROR: Show folder not found: {show_dir}")
        raise SystemExit(1)

    old_dir = (show_dir / "OLD").resolve()
    if not old_dir.is_dir():
        print(f"ERROR: OLD folder not found: {old_dir}")
        raise SystemExit(1)

    # Determine report path
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
    else:
        report_path = find_latest_report(show_dir, showcode)
        if report_path is None:
            print(f"ERROR: No report found matching '{showcode}_*.csv' in {show_dir}")
            raise SystemExit(1)

    if not report_path.is_file():
        print(f"ERROR: Report file not found: {report_path}")
        raise SystemExit(1)

    print(f"Show folder:   {show_dir}")
    print(f"OLD folder:    {old_dir}")
    print(f"Using report:  {report_path}")
    print(f"Mode:          {'DRY-RUN' if args.dry_run else 'EXECUTE'}")
    print(f"Keep OLD:      {'YES (copy back, do not delete)' if args.keep_old else 'NO (move back, then delete OLD)'}\n")

    restored = 0
    missing_backups = 0
    errors = 0

    with open(report_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("action") or "").strip() != "updated":
                continue

            backup_path_str = (row.get("backup_path") or "").strip()
            file_path_str = (row.get("file_path") or "").strip()
            if not backup_path_str or not file_path_str:
                print(f"SKIP (row missing paths): {row}")
                continue

            backup_path = Path(backup_path_str).expanduser().resolve()
            dest_path = Path(file_path_str).expanduser().resolve()

            # Sanity: ensure both paths live under this show's folder
            if not validate_under(show_dir, backup_path):
                print(f"SKIP (backup not under show dir): {backup_path}")
                continue
            if not validate_under(show_dir, dest_path):
                print(f"SKIP (destination not under show dir): {dest_path}")
                continue

            if not backup_path.exists():
                print(f"MISS backup (not found): {backup_path}")
                missing_backups += 1
                continue

            # Ensure destination parent exists
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            if args.dry_run:
                print(f"Would restore: {backup_path}  ->  {dest_path}")
                restored += 1
                continue

            try:
                if args.keep_old:
                    # Copy back, keeping the backup in OLD
                    tmp = dest_path.parent / f".__tmp_restore_{dest_path.name}"
                    shutil.copyfile(backup_path, tmp)
                    os.replace(tmp, dest_path)
                else:
                    # Move back (removes backup from OLD)
                    os.replace(backup_path, dest_path)

                print(f"RESTORED: {dest_path}")
                restored += 1
            except Exception as e:
                print(f"ERROR restoring {dest_path}: {e}")
                errors += 1

    # Delete OLD folder if we are not keeping it and not in dry-run
    if not args.dry_run and not args.keep_old:
        try:
            shutil.rmtree(old_dir)
            print(f"\nOLD folder deleted: {old_dir}")
        except Exception as e:
            print(f"\nWARNING: Failed to delete OLD folder ({old_dir}): {e}")

    print("\n================ SUMMARY ================\n")
    print(f"Restored (planned if dry-run): {restored}")
    print(f"Missing backups:              {missing_backups}")
    print(f"Errors:                       {errors}")
    print("\nDone.")


if __name__ == "__main__":
    main()
