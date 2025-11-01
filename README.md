# **Cover Replacement Automation Tool**

MORE DETAILED DOCUMENTATION COMING SOON!

This repository contains two Python scripts that automate first-page replacement and restoration across large collections of PDF score files. The tools are designed for workflows in music publishing, where each show has multiple files requiring consistent first-page covers replacements.

**Overview**

The repository includes:

* `replacecovers.py` — replaces the first page of each target PDF with a new cover page and optionally adds a blank page after it.
* `reverse_replacecovers.py` — restores the original PDF by reversing the operation, bringing back the previous first page from backup files.
* `settings.json` — configuration file controlling how the scripts determine what is important vs. unimportant content when performing blanking of the second page.

Some features, like blanking of the second page, are design for legacy titles that have incorrectly stuff written on the second page. It has to be either blanked moved to the second page.

**Features**

* Automatically replaces the first page of multiple PDFs in bulk.
* Detects and preserves key pages (e.g., “Table of Contents,” “Song List,” “Orchestration”).
* Optionally inserts a blank second page after the replacement.
* Skips files containing important sections to avoid overwriting critical information.
* Creates automatic backups of all originals before modification.
* Generates detailed terminal reports for every processed file.
* Reversible: use `reverse_replacecovers.py` to restore the originals from backups in /OLD.

**How It Works**

The script reads configuration values from settings.json, then iterates over all PDFs in the specified show folders.
For each file, it:

1. Checks for important or unimportant keywords to decide whether to blank the second page.
2. Creates a backup copy in an OLD subdirectory.
3. Inserts a new cover page (provided separately in 'covers').
4. Optionally adds a blank second page if enabled.
5. Logs all results in the terminal, marking each operation as OK or Skipped.

Example Output:

```CLI 
✅ OK: FGDT-PC.pdf — page 1 replaced; page 2 blanked ⬜ (backup → /shows/BEEH/OLD)"`
⚠️ Skipped: UYYU-PC.pdf — contains 'Table of Contents'
```

**File Structure**

```
├── replacecovers.py
├── reverse_replacecovers.py
├── settings.json
├── covers/
│   ├── [SHOWCODE]-COVER.pdf
├── shows/
│   ├── [SHOWCODE]/
│   │   ├── [SHOWCODE]-*.pdf
│   │   └── OLD/ (auto-created for backups) ```
```

**Configuration (settings.json)**

The configuration file defines text-detection logic and behavioral flags:

| Key                           | Type    | Description                                                  |
| ----------------------------- | ------- | ------------------------------------------------------------ |
| `enable_blank_second`         | Boolean | If true, adds a blank second page after replacement.         |
| `enable_preserve_insert`      | Boolean | If true, preserves certain inserts (e.g., indexes).          |
| `unimportant_keywords`        | Array   | Words/phrases identifying pages that can be safely replaced. |
| `important_keywords`          | Array   | Words/phrases that protect a page from being replaced.       |
| `max_short_unimportant_chars` | Integer | Character limit for short unimportant text.                  |
| `max_short_unimportant_lines` | Integer | Line limit for short unimportant text.                       |
| `important_min_words`         | Integer | Word threshold above which a page is considered important.   |
| `important_min_lines`         | Integer | Line threshold for an important page.                        |
| `important_long_line_chars`   | Integer | Minimum line length for detecting long important text.       |

You can adjust these thresholds to match your library’s formatting conventions.

**Usage**

1. Replace Covers

Run the following command:

```bash
py replacecovers.py --covers "/replace-covers/covers" --root "replacecovers/shows" --showcode FGDT
```

Or any showcode (ABCD, BDFD etc.) - I used ADDA as an example.

This script:

* Reads all PDF files in the /shows directory.

* Replaces the first page with the corresponding cover from /covers.

* Creates a backup of the original version in /shows/[SHOWCODE]/OLD. Duplicate names will have "_2" added.


2. Reverse Replacement

If you need to restore the originals:

```bash
python reverse_replacecovers.py --root "replacecovers/shows" --showcode FGDT
```

This script:

* Looks for backups in each show’s OLD folder.

* Uses the csv file that has original folder data.

* Restores them to their original file paths, overwriting the modified versions. Duplicate names will have "_2" removed as they go back to their original folders.


Libraries:

PyPDF2

os, json, re, sys, tqdm 


**Example Workflow**

1. Place all original PDFs names SHOWCODE-* in /shows/SHOWCODE/.
2. Place the new cover PDF as /covers/SHOWCODE-*.pdf.
3. Review and adjust `settings.json` if needed.
4. Run `replacecovers.py` to perform replacements.
5. Verify results and logs.
6. Use `reverse_replacecovers.py` to restore files if necessary.

Every modification automatically generates a backup in /OLD/.

The script never deletes files; it only replaces or copies.

You can always restore all originals using the reverse script. DO NOT DETELE the csv log file.

Example Terminal Session

```CLI
Starting cover replacement process...
Found 120 files to process.

✅ OK: FGDT-PC.pdf — page 1 replaced; page 2 blanked
⚠️ Skipped: GREASE-PC.pdf — detected “Table of Contents”
✅ OK: FGDT-DS.pdf — page 1 replaced
Backup created in /shows/FGDT/OLD/

Process complete. 118 files updated, 2 skipped.
```

License: MIT

Author

Ernie Bird, Director of Music, Theatrical Rights Worldwide


