$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$manifestPath = Join-Path $workspace 'storage/batches/s14_all_manifest.json'
$outputDirectory = Join-Path $workspace 'storage/exports/消費税の闇_S14_全20話'
$summaryPath = Join-Path $outputDirectory '生成状況.json'
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

while ($true) {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $results = [System.Collections.Generic.List[object]]::new()
    foreach ($episode in $manifest.episodes) {
        $projectDir = Join-Path $workspace "storage/projects/$($episode.project_id)"
        $status = Get-Content -LiteralPath (Join-Path $projectDir 'status.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $safeTitle = ([string]$episode.title -replace '[\\/:*?"<>|]', '_').Trim()
        $destination = Join-Path $outputDirectory ("S14-{0}_{1}.mp4" -f $episode.number, $safeTitle)
        if ($status.status -eq 'completed') {
            $source = Join-Path $projectDir 'final/final.mp4'
            if ((Test-Path -LiteralPath $source) -and
                (-not (Test-Path -LiteralPath $destination) -or
                 (Get-Item -LiteralPath $source).Length -ne (Get-Item -LiteralPath $destination).Length)) {
                Copy-Item -LiteralPath $source -Destination $destination -Force
            }
        }
        $results.Add([pscustomobject]@{
            number = $episode.number
            title = $episode.title
            project_id = $episode.project_id
            status = $status.status
            message = $status.message
            file = if (Test-Path -LiteralPath $destination) { Split-Path -Leaf $destination } else { '' }
        })
    }
    [pscustomobject]@{
        updated_at = (Get-Date).ToString('o')
        output_directory = $outputDirectory
        episodes = @($results.ToArray())
    } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $summaryPath -Encoding UTF8
    if ($results.Count -eq 20 -and @($results | Where-Object status -NotIn @('completed', 'failed', 'cancelled')).Count -eq 0) { break }
    Start-Sleep -Seconds 30
}
