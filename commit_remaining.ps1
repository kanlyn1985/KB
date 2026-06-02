$ErrorActionPreference = "Stop"
cd E:\AI_Project\opencode_workspace\KB1

Write-Host "=== Committing remaining files ===" -ForegroundColor Cyan

# Commit 1: gitattributes + normalize line endings
Write-Host "`n--- Commit 1: gitattributes and line-ending normalization ---" -ForegroundColor Yellow
git add .gitattributes
git add .agents/ .codestable/reference/ .codestable/tools/ .codestable/compound/ .codestable/onboard-audit.md docs/ tests/generated/
git commit -m "chore: add gitattributes for LF normalization, normalize line endings"

# Commit 2: remaining untracked source files
Write-Host "`n--- Commit 2: remaining source files ---" -ForegroundColor Yellow
git add src/enterprise_agent_kb/
git commit -m "feat: add remaining enterprise_agent_kb modules"

# Commit 3: remaining untracked test files
Write-Host "`n--- Commit 3: remaining test files ---" -ForegroundColor Yellow
git add tests/
git commit -m "test: add remaining test files"

# Commit 4: remaining untracked project files
Write-Host "`n--- Commit 4: project config files ---" -ForegroundColor Yellow
git add .github/ .opencode/ AGENTS.md LICENSE README.md pyproject.toml pytest.ini skills-lock.json scripts/ launch.ps1 start_demo.bat
git commit -m "chore: add project config, scripts, and documentation files"

# Final status
Write-Host "`n=== Done. Final status: ===" -ForegroundColor Cyan
git status --short
git log --oneline -5
