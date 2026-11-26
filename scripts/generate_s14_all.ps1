param(
    [switch]$Submit,
    [string]$TemplateProjectId = '20261023_042718_d3bd4ac3'
)

$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$sourcePath = Join-Path $workspace 'frontend/src/s14_chuusa_qa_01_20.md'
$templatePath = Join-Path $workspace "storage/projects/$TemplateProjectId/project.json"
$manifestPath = Join-Path $workspace 'storage/batches/s14_all_manifest.json'
$source = Get-Content -LiteralPath $sourcePath -Raw -Encoding UTF8
$template = Get-Content -LiteralPath $templatePath -Raw -Encoding UTF8 | ConvertFrom-Json
$headings = [regex]::Matches($source, '(?m)^##\s+S14-(\d{2})([^\r\n]*)$')
if ($headings.Count -ne 20) { throw "S14は20話のはずですが、$($headings.Count)話です。" }

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
        if ($current.Count -eq 0 -or -not $line -or $line -eq '---' -or
            $line.StartsWith('#') -or $line.StartsWith('```') -or
            $line.StartsWith('>') -or $line -match '^\*\*.+\*\*$') { continue }
        $current.Add($line)
    }
    if ($current.Count -gt 0) { $blocks.Add(($current -join "`n")) }
    return ($blocks -join "`n`n")
}

$existing = @{}
if (Test-Path -LiteralPath $manifestPath) {
    $oldManifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($entry in $oldManifest.episodes) { $existing[[string]$entry.number] = $entry }
}
$episodes = [System.Collections.Generic.List[object]]::new()
for ($i = 0; $i -lt $headings.Count; $i++) {
    $heading = $headings[$i]
    $number = $heading.Groups[1].Value
    if ($number -ne ('{0:D2}' -f ($i + 1))) { throw "話数の順序が不正です: $number" }
    $end = if ($i + 1 -lt $headings.Count) { $headings[$i + 1].Index } else { $source.Length }
    $section = $source.Substring($heading.Index + $heading.Length, $end - $heading.Index - $heading.Length)
    $title = $heading.Groups[2].Value.Trim().Trim('「', '」', ' ', '（', '）')
    $script = Get-SceneScript $section
    $count = [regex]::Matches($script, '(?m)^映像：').Count
    if ($count -lt 3 -or $script -match '\[start_frame:DXおじさん(?:2)?\.jpg\]') {
        throw "S14-$number の台本または画像指定が不正です（シーン数=$count）。"
    }
    if ($existing.ContainsKey($number)) {
        $entry = $existing[$number]
        $saved = Get-Content -LiteralPath (Join-Path $workspace "storage/projects/$($entry.project_id)/project.json") -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($saved.script -cne $script) { throw "S14-$number は登録後に台本が変更されています。二重登録を避けるため停止します。" }
        $episodes.Add($entry)
        Write-Output "EXISTS S14-$number $($entry.project_id)"
        continue
    }
    $payload = $template.PSObject.Copy()
    foreach ($name in @('project_id', 'created_at', 'updated_at')) { $payload.PSObject.Properties.Remove($name) }
    $payload.title = "消費税の闇 S14 中佐Q&A｜#$number｜$title"
    $payload.prompt = "消費税の闇 S14 中佐Q&A #$number「$title」。税と社会保険料の負担を、体験談と制度の説明に分けて検証するショート。台本指定どおりに生成する。"
    $payload.script = $script
    if (-not $Submit) {
        Write-Output "READY S14-$number scenes=$count $title"
        continue
    }
    $body = $payload | ConvertTo-Json -Depth 30 -Compress
    $response = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:18000/api/projects' -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
    $entry = [pscustomobject]@{ number = $number; title = $title; project_id = $response.project_id }
    $episodes.Add($entry)
    [pscustomobject]@{ series = 'S14'; template_project_id = $TemplateProjectId; episodes = @($episodes.ToArray()) } |
        ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    Write-Output "QUEUED S14-$number $($response.project_id)"
}
