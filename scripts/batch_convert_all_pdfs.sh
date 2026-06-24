#!/bin/bash
# Batch convert all PDFs in tmp/ to no-background HTML, sequentially.
# Run this after the current p1-20 task finishes.
set -e

PDF_DIR="/home/evt/projects/KB1/tmp"
OUT_DIR="/home/evt/projects/KB1/output"
WORK_DIR="/tmp/ppstruct_test/vl_cache"
PY="/home/evt/projects/KB1/.venv-paddle/bin/python"
SCRIPT="/home/evt/projects/KB1/scripts/ocr_layout_to_html.py"
LOG_FILE="/home/evt/projects/KB1/output/batch_convert.log"

echo "========================================" | tee "$LOG_FILE"
echo "Batch convert started: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

cd /home/evt/projects/KB1

# --- Task 1: Full GBT+18487.1-2023.pdf (157 pages) ---
PDF="$PDF_DIR/GBT+18487.1-2023.pdf"
OUT="$OUT_DIR/layout_restored_gbt18487_full_nobg.html"
echo "" | tee -a "$LOG_FILE"
echo "[1/2] Converting $PDF (157 pages)..." | tee -a "$LOG_FILE"
echo "     Output: $OUT" | tee -a "$LOG_FILE"
echo "     Started: $(date)" | tee -a "$LOG_FILE"
$PY "$SCRIPT" "$PDF" \
    --pages 1-157 \
    --work-dir "$WORK_DIR" \
    --output "$OUT" \
    --no-background 2>&1 | tee -a "$LOG_FILE"
echo "     Finished: $(date)" | tee -a "$LOG_FILE"
echo "     Size: $(ls -la "$OUT" 2>/dev/null | awk '{print $5}') bytes" | tee -a "$LOG_FILE"

# --- Task 2: sample_parse.pdf ---
PDF="$PDF_DIR/sample_parse.pdf"
OUT="$OUT_DIR/layout_restored_sample_parse_nobg.html"
# Use a separate work dir to avoid VL cache collisions
SAMPLE_WORK_DIR="/tmp/ppstruct_sample_parse"
mkdir -p "$SAMPLE_WORK_DIR"
echo "" | tee -a "$LOG_FILE"
echo "[2/2] Converting $PDF (1 page)..." | tee -a "$LOG_FILE"
echo "     Output: $OUT" | tee -a "$LOG_FILE"
echo "     Started: $(date)" | tee -a "$LOG_FILE"
$PY "$SCRIPT" "$PDF" \
    --pages 1-1 \
    --work-dir "$SAMPLE_WORK_DIR" \
    --output "$OUT" \
    --no-background 2>&1 | tee -a "$LOG_FILE"
echo "     Finished: $(date)" | tee -a "$LOG_FILE"
echo "     Size: $(ls -la "$OUT" 2>/dev/null | awk '{print $5}') bytes" | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "Batch convert completed: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
