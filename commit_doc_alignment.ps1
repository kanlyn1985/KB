# commit_doc_alignment.ps1
# Commit all documentation alignment changes
# Generated: 2026-05-19

$ErrorActionPreference = "Stop"
$projectRoot = "E:\AI_Project\opencode_workspace\KB1"

Set-Location $projectRoot

# Step 1: Fix git index if corrupted
Write-Host "=== Step 1: Reset git index ===" -ForegroundColor Cyan
if (Test-Path ".git\index.lock") {
    Remove-Item ".git\index.lock" -Force
    Write-Host "Removed stale .git\index.lock" -ForegroundColor Yellow
}

# Reset the staged deletions (from previous corrupted reset)
git reset HEAD
Write-Host "Git index reset complete" -ForegroundColor Green

# Step 2: Add all changes
Write-Host ""
Write-Host "=== Step 2: Stage all changes ===" -ForegroundColor Cyan
git add -A
$status = git status --short
$changeCount = ($status | Measure-Object).Count
Write-Host "Staged $changeCount changes" -ForegroundColor Green

# Step 3: Commit
Write-Host ""
Write-Host "=== Step 3: Commit ===" -ForegroundColor Cyan
git commit -m "docs: code-doc alignment, archive historical docs, add next-phase roadmap

- ARCHITECTURE.md: filled from skeleton with full 68-module inventory
- VISION.md: added priority levels (P0/P1/long-term) and dependency diagram
- Moved 55 historical docs from docs/ root to docs/_archive/
- Added kb1-next-phase roadmap (ontology phase 1, audit closure, answer quality)
- Updated audit index with F-04/F-05 open items status
- Added code-doc gap analysis section to ARCHITECTURE.md"

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "Run 'git log --oneline -3' to verify the commit."
