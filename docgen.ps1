# docgen quick start for Windows — run docgen without activating anything.
#
#   .\docgen.ps1                                          show what you can run right now
#   .\docgen.ps1 all MySolution.zip --no-llm -o out\      full doc set from a solution export
#   .\docgen.ps1 all Workshop.txt --no-llm -o out\        full doc set from a meeting transcript
#   .\docgen.ps1 --help                                   the CLI's own help
#
# Every argument is passed straight through to docgen, so anything in
# docs\USAGE.md works here unchanged. The virtual environment is created on
# first run if it does not exist yet.
#
# Prefer typing plain `docgen`? Activate the environment in your shell instead:
#   .\.venv\Scripts\Activate.ps1

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot
$docgenExe = Join-Path $repo ".venv\Scripts\docgen.exe"

# --- ensure the environment exists -----------------------------------------

if (-not (Test-Path $docgenExe)) {
    Write-Host "docgen is not installed in .venv yet - running setup..." -ForegroundColor Yellow
    & (Join-Path $repo "setup.ps1")
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $docgenExe)) {
        Write-Host "Setup did not complete. Run .\setup.ps1 on its own to see why." -ForegroundColor Red
        exit 1
    }
    Write-Host ""
}

# --- no arguments: show a quick start using the files actually present ------

if ($args.Count -eq 0) {
    Write-Host "== docgen quick start ==" -ForegroundColor Cyan
    & $docgenExe --version
    Write-Host ""

    $zips = @(Get-ChildItem -Path $repo -Filter *.zip -File -ErrorAction SilentlyContinue |
              Select-Object -First 3)
    $transcripts = @(Get-ChildItem -Path $repo -File -ErrorAction SilentlyContinue |
                     Where-Object { $_.Extension -in ".txt", ".vtt" -and $_.Name -ne "requirements.txt" } |
                     Select-Object -First 3)

    Write-Host "Generate the full document set, fully offline:"
    Write-Host ""
    if ($zips.Count -gt 0) {
        Write-Host "  From a solution export:" -ForegroundColor Green
        foreach ($z in $zips) {
            Write-Host "    .\docgen.ps1 all `"$($z.Name)`" --no-llm -o out\"
        }
    } else {
        Write-Host "  From a solution export:" -ForegroundColor Green
        Write-Host "    .\docgen.ps1 all MySolution.zip --no-llm -o out\"
        Write-Host "    (no .zip found in this folder - copy your solution export here)" -ForegroundColor DarkGray
    }
    Write-Host ""
    if ($transcripts.Count -gt 0) {
        Write-Host "  From a meeting transcript:" -ForegroundColor Green
        foreach ($t in $transcripts) {
            Write-Host "    .\docgen.ps1 all `"$($t.Name)`" --no-llm -o out\"
        }
    } else {
        Write-Host "  From a meeting transcript (Teams .txt, .vtt, or a workshop write-up):" -ForegroundColor Green
        Write-Host "    .\docgen.ps1 all Workshop.txt --no-llm -o out\"
        Write-Host "    (no .txt or .vtt found in this folder - copy your transcript here)" -ForegroundColor DarkGray
    }

    Write-Host ""
    Write-Host "Useful variations:"
    Write-Host "    .\docgen.ps1 all <input> --no-llm --format md -o out\      Markdown only, no Word"
    Write-Host "    .\docgen.ps1 all <input> --no-llm --docs hld,lld -o out\   just these documents"
    Write-Host "    .\docgen.ps1 render out\snapshot.json --no-llm -o out\     re-render without re-parsing"
    Write-Host "    .\docgen.ps1 diff old\snapshot.json new\snapshot.json -o diff\   release notes"
    Write-Host "    .\docgen.ps1 --help                                        every command and option"
    Write-Host ""
    Write-Host "Drop branded Word templates in templates\ (HLD.docx, LLD.docx, Meeting Notes.docx)"
    Write-Host "to style individual documents - see templates\README.md."
    Write-Host ""
    Write-Host "Optional LLM narrative tier (drafts prose; omit --no-llm):"
    Write-Host "    `$env:ANTHROPIC_API_KEY = '<your key>'"
    Write-Host "    .\docgen.ps1 all <input> -o out\"
    Write-Host ""
    Write-Host "Docs: README.md (overview) - docs\USAGE.md (full reference)"
    exit 0
}

# --- forward everything to the CLI -----------------------------------------

# Two Windows argument-passing traps are smoothed out here so that the examples
# in the help text behave the way they read:
#
# 1. PowerShell parses a bareword like `md,docx` as an *array* of two strings,
#    and splatting would then hand docgen two separate arguments. Rejoin any
#    such argument with commas, so `--docs meeting-notes,actions` means what it
#    looks like it means.
# 2. A trailing backslash inside a quoted argument -- `-o "My Client\"` -- is
#    read by the C runtime as an escaped quote, and the path arrives mangled.
#    Trailing separators are meaningless on a folder argument, so drop them.
function Convert-DocgenArgument {
    param($Argument)

    if ($Argument -is [System.Array]) {
        $text = ($Argument | ForEach-Object { [string]$_ }) -join ','
    } else {
        $text = [string]$Argument
    }
    if ($text.Length -gt 1 -and $text -notmatch '"') {
        $text = $text -replace '\\+$', ''
    }
    return $text
}

$forward = @(foreach ($argument in $args) { Convert-DocgenArgument $argument })

& $docgenExe @forward
exit $LASTEXITCODE
