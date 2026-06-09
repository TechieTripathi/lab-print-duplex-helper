# Duplex Print Helper

This project started from a very practical problem in my lab.

We have a printer that can only print on one side of the paper. Many times we still need double-sided printouts, and doing that manually is annoying, error-prone, and wastes time because people have to remember page order, paper rotation, and retry steps. I built this tool so my lab mates can follow a guided workflow and get duplex-style output more reliably from a single-sided printer.

## What It Does

Duplex Print Helper is a local Flask web app that helps users print double-sided documents in two guided passes.

It can:

- accept `PDF` and `DOCX` files from the browser
- convert `DOCX` to `PDF` before printing
- show page count and file metadata before page-range selection
- allow page-range printing like `1-4, 7, 10-12`
- list available CUPS printers
- print even pages first
- guide the user to rotate and reinsert paper
- print odd pages in reverse order so the final document reads correctly
- also support simple single-sided printing

## Why This Exists

This tool is meant for shared local environments like labs, offices, and print stations where:

- the printer does not support automatic duplex printing
- users frequently print multi-page documents
- manual double-sided printing causes confusion
- a lightweight browser UI is easier than remembering print instructions every time

## Requirements

- Ubuntu Linux
- CUPS running locally
- LibreOffice installed for `DOCX` to `PDF` conversion
- Python `3.13`
- `uv`

## Install System Packages

```bash
sudo apt update
sudo apt install cups libcups2-dev libreoffice
```

## Install uv

If `uv` is not installed yet:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then confirm:

```bash
uv --version
```

## Project Setup

This repo uses:

- `pyproject.toml` for project metadata and dependencies
- `uv.lock` for locked dependency resolution
- `.python-version` to pin the local Python version

Install the environment with:

```bash
uv sync
```

## Run The App

```bash
uv run python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

## How To Use

1. Open the web app in your browser.
2. Upload a `PDF` or `DOCX` file.
3. Review the detected page count and file metadata.
4. Optionally enter a page range.
5. Click `Prepare Print File`.
6. Select the printer.
7. Choose `Single-sided` or `Double-sided`.
8. Start printing.
9. If using duplex mode, wait for Pass 1 to finish.
10. Rotate the full stack `180 degrees`, do not flip the pages, then reinsert it.
11. Continue the second pass.

## Notes

- Uploaded and generated files are stored temporarily in `tmp/`
- Workflow state is kept in memory only
- This is a local-network / local-machine utility, not a cloud app
- `DOCX` support depends on LibreOffice being available on the machine
