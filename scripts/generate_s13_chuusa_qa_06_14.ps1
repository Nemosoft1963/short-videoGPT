param(
    [switch]$Submit,
    [switch]$RetryFailed,
    [switch]$RegenerateChanged,
    [string]$TemplateProjectId = '20261004_141245_0c0bd577'
)

$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$sourcePath = Join-Path $workspace 'frontend/src/s13_chuusa_qa_04_14.md'
$templatePath = Join-Path $workspace "storage/projects/$TemplateProjectId/project.json"
$source = Get-Content -LiteralPath $sourcePath -Raw -Encoding UTF8
$template = Get-Content -LiteralPath $templatePath -Raw -Encoding UTF8 | ConvertFrom-Json
$headingPattern = '(?m)^##\s+S13-(\d{2})([^\r\n]*)$'
$headings = [regex]::Matches($source, $headingPattern)

function Get-SceneScript([string]$section) {
    $blocks = [System.Collections.Generic.List[string]]::new()
    $current = [System.Collections.Generic.List[string]]::new()
    foreach ($rawLine in ($section -split '\r?\n')) {
        $line = $rawLine.Trim()
        if ($line.StartsWith('映像：')) {
            if ($current.Count -gt 0) { $blocks.Add(($current -join "`n")) }
            $current.Clear()
            $current.Add($line)
            continue
        }
        if ($current.Count -eq 0 -or -not $line -or $line -eq '---' -or $line.StartsWith('#') -or $line.StartsWith('```') -or $line.StartsWith('>') -or $line -match '^\*\*.+\*\*$') { continue }
        $current.Add($line)
    }
    if ($current.Count -gt 0) { $blocks.Add(($current -join "`n")) }
    return ($blocks -join "`n`n")
}

$entries = [ordered]@{}
for ($i = 0; $i -lt $headings.Count; $i++) {
    $heading = $headings[$i]
    $number = $heading.Groups[1].Value
    $end = if ($i + 1 -lt $headings.Count) { $headings[$i + 1].Index } else { $source.Length }
    $section = $source.Substring($heading.Index + $heading.Length, $end - $heading.Index - $heading.Length)
    $title = $heading.Groups[2].Value.Trim().Trim('「', '」', ' ', '（', '）')
    $entries[$number] = [pscustomobject]@{ title = $title; script = (Get-SceneScript $section) }
}

$existing = @{}
Get-ChildItem -LiteralPath (Join-Path $workspace 'storage/projects') -Directory | Sort-Object Name | ForEach-Object {
    $projectPath = Join-Path $_.FullName 'project.json'
    if (Test-Path -LiteralPath $projectPath) {
        try {
            $project = Get-Content -LiteralPath $projectPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($project.title -match '^消費税の闇 S13 中佐Q&A｜#(\d{2})｜') { $existing[$matches[1]] = $_.Name }
        } catch { }
    }
}

foreach ($number in 4..14 | ForEach-Object { '{0:D2}' -f $_ }) {
    if ($existing.ContainsKey($number)) {
        $existingId = $existing[$number]
        $existingDirectory = Join-Path $workspace "storage/projects/$existingId"
        $status = Get-Content -LiteralPath (Join-Path $existingDirectory 'status.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $existingProject = Get-Content -LiteralPath (Join-Path $existingDirectory 'project.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $scriptChanged = ($existingProject.script -replace "`r`n", "`n").Trim() -cne $entries[$number].script.Trim()
        if (-not (($RetryFailed -and $status.status -eq 'failed') -or ($RegenerateChanged -and $scriptChanged))) {
            Write-Output "S13-$number exists: $existingId ($($status.status))"
            continue
        }
    }
    $entry = $entries[$number]
    if (-not $entry -or ([regex]::Matches($entry.script, '(?m)^映像：')).Count -ne 5) { throw "S13-$number の5シーンを確認できません。" }
    $payload = $template.PSObject.Copy()
    foreach ($name in @('project_id', 'created_at', 'updated_at')) { $payload.PSObject.Properties.Remove($name) }
    $payload.title = "消費税の闇 S13 中佐Q&A｜#$number｜$($entry.title)"
    $payload.head_title = $payload.title
    $payload.prompt = "消費税の闇 S13 中佐Q&A #$number「$($entry.title)」。あずかり金という虚構を一次資料と制度構造から検証するショート。台本指定どおりに生成する。"
    $payload.script = $entry.script
    if (-not $Submit) { Write-Output "READY S13-$number $($payload.title)"; continue }
    $body = $payload | ConvertTo-Json -Depth 30 -Compress
    $response = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18000/api/projects' -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
    Write-Output "QUEUED S13-$number $($response.project_id)"
}
