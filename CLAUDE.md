# CLAUDE.md

This file provides guidance for AI assistants working on this repository.

## Repository Overview

This repository contains a single PowerShell installation script (`install.ps1`) that bootstraps Claude Code on Windows. It is a **distribution artifact**, not a traditional software project — there is no build system, package manifest, or test suite.

**Intended one-liner usage for end users:**
```powershell
irm https://claude.ai/install.ps1 | iex
```

## File Structure

```
/
├── install.ps1    # Windows installer script (the entire product)
└── CLAUDE.md      # This file
```

## Technology Stack

- **Language**: PowerShell 5.0+
- **Platform target**: Windows 10/11 (64-bit or 32-bit)
- **Runtime dependency installed**: Node.js 18+ LTS
- **Package installed**: `@anthropic-ai/claude-code` (global npm install)

## What `install.ps1` Does

1. **OS guard** — exits with an error message on non-Windows platforms
2. **PowerShell version check** — requires PS 5.0+
3. **Existing Claude Code detection** — warns and checks for updates if already installed
4. **Node.js detection and installation** with a three-tier fallback:
   - `winget install OpenJS.NodeJS.LTS` (preferred, built into Windows 10/11)
   - `choco install nodejs-lts` (if Chocolatey is available)
   - Direct `.msi` download from `nodejs.org/dist/lts/` (ultimate fallback)
5. **npm validation** — confirms npm is accessible after Node.js setup
6. **Claude Code installation** — `npm install -g @anthropic-ai/claude-code`
7. **PATH refresh** — updates the current session's `$env:PATH` so `claude` is immediately available
8. **Verification** — runs `claude --version` to confirm success

## Code Conventions

### PowerShell Style
- `$ErrorActionPreference = 'Stop'` is set globally so unhandled errors terminate the script
- Function names follow PowerShell `Verb-Noun` convention (e.g., `Get-NodeVersion`, `Install-Node`, `Test-NodeMinVersion`)
- Helper output functions (`Write-Header`, `Write-Step`, `Write-Success`, `Write-Warn`, `Write-Fail`) wrap `Write-Host` with consistent color coding:
  - Cyan — headers / call-to-action
  - White — steps / informational
  - Green — success
  - Yellow — warnings
  - Red — failures
- Error suppression is explicit and scoped (`2>$null`, `2>&1`) rather than global
- Exit codes: `exit 1` for all failure paths; implicit `exit 0` on success

### What to Avoid
- Do not introduce dependencies on external modules (e.g., `PSReadLine`, third-party modules)
- Do not assume a package manager is present; the winget → choco → direct-download chain must be preserved
- Do not break the `irm … | iex` execution model — the script must work when piped directly from a URL with no local file

## Development Workflow

There is no build step. To test changes:
1. Edit `install.ps1` locally
2. Run on a Windows machine (or VM) in various states:
   - No Node.js installed
   - Old Node.js (< v18) installed
   - Node.js v18+ already installed
   - Claude Code already installed
3. Verify all exit paths and output messages are correct

There is no CI/CD configuration in this repository.

## Git Branches

| Branch | Purpose |
|--------|---------|
| `claude/add-powershell-install-script-Cmest` | Branch that added `install.ps1` |
| `claude/add-claude-documentation-EY4QH` | Branch adding this CLAUDE.md |

The repository has a single upstream commit. Development branches are feature branches intended for review and merge.

## Key Constraints for AI Assistants

- **Windows-only script** — do not add Linux/macOS logic; the OS check at the top intentionally exits on non-Windows
- **No new files** unless explicitly required — the project should remain minimal
- **Preserve fallback chain** — any Node.js installation changes must keep winget → choco → MSI order
- **Keep output consistent** — new steps should use the existing `Write-Step`/`Write-Success`/`Write-Warn`/`Write-Fail` helpers
- **Test all code paths** — because there is no automated test suite, changes must be manually verified across the installation states listed above
