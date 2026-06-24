#!/bin/bash
# Wait for the currently running p1-20 background task to finish, then run batch convert.
# This script polls for the output HTML file to be updated (newer than 21:03).

LOG="/home/evt/projects/KB1/output/wait_and_batch.log"
echo "Waiting for current p1-20 task to finish... $(date)" | tee "$LOG"

# The current task writes to output/layout_restored_gbt18487_p1-20_nobg.html
# It was last modified at 20:53. Wait until it's modified again (task done).
TARGET="/home/evt/projects/KB1/output/layout_restored_gbt18487_p1-20_nobg.html"
OLD_MTIME=$(stat -c %Y "$TARGET" 2>/dev/null || echo 0)
echo "Initial mtime: $OLD_MTIME" | tee -a "$LOG"

while true; do
    NEW_MTIME=$(stat -c %Y "$TARGET" 2>/dev/null || echo 0)
    if [ "$NEW_MTIME" != "$OLD_MTIME" ]; then
        echo "File updated! mtime=$NEW_MTIME  $(date)" | tee -a "$LOG"
        break
    fi
    # Also check if the python process is still running
    if ! pgrep -f "ocr_layout_to_html.py.*pages 1-20" > /dev/null 2>&1; then
        echo "Process no longer running. Checking file mtime..." | tee -a "$LOG"
        NEW_MTIME=$(stat -c %Y "$TARGET" 2>/dev/null || echo 0)
        if [ "$NEW_MTIME" != "$OLD_MTIME" ]; then
            echo "File updated! mtime=$NEW_MTIME  $(date)" | tee -a "$LOG"
        else
            echo "WARNING: Process ended but file not updated. Proceeding anyway. $(date)" | tee -a "$LOG"
        fi
        break
    fi
    sleep 30
done

echo "" | tee -a "$LOG"
echo "Starting batch convert... $(date)" | tee -a "$LOG"
bash /home/evt/projects/KB1/scripts/batch_convert_all_pdfs.sh 2>&1 | tee -a "$LOG"
echo "All done. $(date)" | tee -a "$LOG"
