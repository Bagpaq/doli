# Claude Code Installer for Windows
# Usage: irm https://claude.ai/install.ps1 | iex

$ErrorActionPreference = 'Stop'

function Write-Header {
    Write-Host ""
    Write-Host "  Claude Code Installer" -ForegroundColor Cyan
    Write-Host "  ─────────────────────" -ForegroundColor DarkGray
    Write-Host ""
}

function Write-Step {
    param([string]$Message)
    Write-Host "  → $Message" -ForegroundColor White
}

function Write-Success {
    param([string]$Message)
    Write-Host "  ✓ $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "  ! $Message" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Message)
    Write-Host "  ✗ $Message" -ForegroundColor Red
}

function Get-NodeVersion {
    try {
        $version = & node --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $version) {
            return $version.TrimStart('v')
        }
    } catch {}
    return $null
}

function Get-NpmVersion {
    try {
        $version = & npm --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $version) {
            return $version
        }
    } catch {}
    return $null
}

function Test-NodeMinVersion {
    param([string]$Version, [int]$MinMajor = 18)
    $major = [int]($Version -split '\.')[0]
    return $major -ge $MinMajor
}

function Install-NodeWithWinget {
    Write-Step "Installing Node.js via winget..."
    try {
        winget install --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements --silent
        if ($LASTEXITCODE -eq 0) {
            # Refresh PATH
            $env:PATH = [System.Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' +
                        [System.Environment]::GetEnvironmentVariable('PATH', 'User')
            return $true
        }
    } catch {}
    return $false
}

function Install-NodeWithChoco {
    Write-Step "Installing Node.js via Chocolatey..."
    try {
        choco install nodejs-lts -y 2>$null
        if ($LASTEXITCODE -eq 0) {
            $env:PATH = [System.Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' +
                        [System.Environment]::GetEnvironmentVariable('PATH', 'User')
            return $true
        }
    } catch {}
    return $false
}

function Install-Node {
    # Try winget first (built into Windows 10/11)
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        if (Install-NodeWithWinget) { return $true }
    }

    # Try Chocolatey
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        if (Install-NodeWithChoco) { return $true }
    }

    # Fallback: direct download
    Write-Step "Downloading Node.js installer..."
    $arch = if ([Environment]::Is64BitOperatingSystem) { 'x64' } else { 'x86' }
    $nodeUrl = "https://nodejs.org/dist/lts/node-lts-$arch.msi"
    $installer = Join-Path $env:TEMP "node-lts-$arch.msi"

    try {
        Invoke-WebRequest -Uri $nodeUrl -OutFile $installer -UseBasicParsing
        Write-Step "Running Node.js installer (this may take a moment)..."
        Start-Process msiexec.exe -Wait -ArgumentList "/i `"$installer`" /quiet /norestart"
        Remove-Item $installer -Force -ErrorAction SilentlyContinue

        $env:PATH = [System.Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' +
                    [System.Environment]::GetEnvironmentVariable('PATH', 'User')
        return $true
    } catch {
        return $false
    }
}

function Install-ClaudeCode {
    Write-Step "Installing Claude Code..."
    try {
        & npm install -g @anthropic-ai/claude-code 2>&1 | Out-Null
        return $LASTEXITCODE -eq 0
    } catch {}
    return $false
}

function Get-ClaudeVersion {
    try {
        $version = & claude --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $version) {
            return $version.Trim()
        }
    } catch {}
    return $null
}

# ── Main ────────────────────────────────────────────────────────────────────

Write-Header

# OS check
if (-not [System.Environment]::OSVersion.Platform.ToString().StartsWith('Win')) {
    Write-Fail "This installer is for Windows only."
    Write-Host "  For macOS/Linux, run:" -ForegroundColor DarkGray
    Write-Host "    npm install -g @anthropic-ai/claude-code" -ForegroundColor DarkGray
    exit 1
}

# PowerShell version check
if ($PSVersionTable.PSVersion.Major -lt 5) {
    Write-Fail "PowerShell 5.0 or later is required (you have $($PSVersionTable.PSVersion))."
    exit 1
}

# Check for existing Claude Code
$existingVersion = Get-ClaudeVersion
if ($existingVersion) {
    Write-Warn "Claude Code $existingVersion is already installed."
    Write-Step "Checking for updates..."
}

# Node.js check
Write-Step "Checking for Node.js..."
$nodeVersion = Get-NodeVersion

if ($nodeVersion) {
    if (Test-NodeMinVersion -Version $nodeVersion) {
        Write-Success "Node.js v$nodeVersion found."
    } else {
        Write-Warn "Node.js v$nodeVersion found, but v18 or later is required."
        Write-Step "Upgrading Node.js..."
        if (-not (Install-Node)) {
            Write-Fail "Failed to upgrade Node.js. Please install Node.js v18+ from https://nodejs.org and re-run this installer."
            exit 1
        }
        $nodeVersion = Get-NodeVersion
        Write-Success "Node.js v$nodeVersion installed."
    }
} else {
    Write-Warn "Node.js not found."
    Write-Step "Installing Node.js (v18 LTS)..."
    if (-not (Install-Node)) {
        Write-Fail "Failed to install Node.js. Please install Node.js v18+ from https://nodejs.org and re-run this installer."
        exit 1
    }
    $nodeVersion = Get-NodeVersion
    if ($nodeVersion) {
        Write-Success "Node.js v$nodeVersion installed."
    } else {
        Write-Fail "Node.js installation could not be verified. Please restart your terminal and re-run this installer."
        exit 1
    }
}

# npm check
$npmVersion = Get-NpmVersion
if (-not $npmVersion) {
    Write-Fail "npm not found. Please ensure Node.js installed correctly, then re-run this installer."
    exit 1
}
Write-Success "npm v$npmVersion found."

# Install Claude Code
Write-Step "Installing @anthropic-ai/claude-code..."
if (-not (Install-ClaudeCode)) {
    Write-Fail "Failed to install Claude Code via npm."
    Write-Host ""
    Write-Host "  Try running manually:" -ForegroundColor DarkGray
    Write-Host "    npm install -g @anthropic-ai/claude-code" -ForegroundColor DarkGray
    exit 1
}

# Refresh PATH so `claude` is available immediately
$env:PATH = [System.Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' +
            [System.Environment]::GetEnvironmentVariable('PATH', 'User')

# Verify
$claudeVersion = Get-ClaudeVersion
if ($claudeVersion) {
    Write-Success "Claude Code $claudeVersion installed successfully."
} else {
    Write-Success "Claude Code installed. You may need to restart your terminal for the 'claude' command to be available."
}

Write-Host ""
Write-Host "  Get started:" -ForegroundColor Cyan
Write-Host "    claude          Launch Claude Code" -ForegroundColor White
Write-Host "    claude --help   Show all commands" -ForegroundColor White
Write-Host ""
Write-Host "  Docs: https://docs.anthropic.com/claude-code" -ForegroundColor DarkGray
Write-Host ""
