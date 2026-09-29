$ErrorActionPreference = "Stop"

$workspace = "C:\Users\kanto\short-videoGPT"
$outputDirectory = "C:\Users\kanto\Downloads\消費税の闇_S13_全30話_v2"
$logDirectory = Join-Path $workspace "storage\batches"
$logPath = Join-Path $logDirectory "s13_v2_batch.log"

$projects = [ordered]@{
    "01" = "20260918_034434_82a5d117"
    "02" = "20260918_035158_c3e25b85"
    "03" = "20260918_035158_72f2fecf"
    "04" = "20260918_035158_58b1b7d0"
    "05" = "20260918_035158_65616122"
    "06" = "20260918_035158_6a01183a"
    "07" = "20260918_035158_38a79471"
    "08" = "20260918_035158_6ca6b55d"
    "09" = "20260918_035158_6fdd49fa"
    "10" = "20260918_035158_37d2f705"
    "11" = "20260918_035158_626d2e29"
    "12" = "20260918_035158_50985581"
    "13" = "20260918_035158_96d8b116"
    "14" = "20260918_035158_f4e600ab"
    "15" = "20260918_035158_5879e0d6"
    "16" = "20260918_035158_4148e43f"
    "17" = "20260918_035158_14ac934a"
    "18" = "20260918_035158_69615827"
    "19" = "20260918_035158_700dead8"
    "20" = "20260918_035158_d96e9a3a"
    "21" = "20260918_035158_3c470388"
    "22" = "20260918_035158_c6c8dc73"
    "23" = "20260918_035158_11932ad4"
    "24" = "20260918_035158_29db2c03"
    "25" = "20260918_035158_0b360101"
    "26" = "20260918_035158_c93d6bee"
    "27" = "20260918_035158_26a868f3"
    "28" = "20260918_035158_e2ad8d78"
    "29" = "20260918_035158_a2af2c08"
    "30" = "20260918_035158_2f856eac"
}

New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

function Write-BatchLog([string]$message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $message
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
}

Write-BatchLog "S13 batch watcher started. projects=$($projects.Count)"

while ($true) {
    $terminalCount = 0

    foreach ($episode in $projects.Keys) {
        $projectId = $projects[$episode]
        $projectDirectory = Join-Path $workspace "storage\projects\$projectId"
        $statusPath = Join-Path $projectDirectory "status.json"
        $projectPath = Join-Path $projectDirectory "project.json"

        if (-not (Test-Path -LiteralPath $statusPath)) {
            continue
        }

        try {
            $status = Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
        }
        catch {
            continue
        }

        if ($status.status -eq "completed") {
            $terminalCount++
            $source = Join-Path $projectDirectory "final\final.mp4"
            $title = ""
            if (Test-Path -LiteralPath $projectPath) {
                try {
                    $project = Get-Content -LiteralPath $projectPath -Raw -Encoding UTF8 | ConvertFrom-Json
                    $title = [string]$project.title
                }
                catch {}
            }
            $shortTitle = ($title -replace '^.*?｜#\d{2}｜', '')
            $safeTitle = ($shortTitle -replace '[\\/:*?"<>|]', '_').Trim()
            if (-not $safeTitle) {
                $safeTitle = "episode_$episode"
            }
            $destination = Join-Path $outputDirectory ("S13-{0}_{1}.mp4" -f $episode, $safeTitle)
            if ((Test-Path -LiteralPath $source) -and -not (Test-Path -LiteralPath $destination)) {
                Copy-Item -LiteralPath $source -Destination $destination
                Write-BatchLog "downloaded episode=$episode project=$projectId file=$destination"
            }
        }
        elseif ($status.status -in @("failed", "cancelled")) {
            $terminalCount++
            $marker = Join-Path $logDirectory ("s13_$episode`_$($status.status).marker")
            if (-not (Test-Path -LiteralPath $marker)) {
                New-Item -ItemType File -Path $marker | Out-Null
                Write-BatchLog "terminal episode=$episode project=$projectId status=$($status.status) message=$($status.message)"
            }
        }
    }

    if ($terminalCount -eq $projects.Count) {
        Write-BatchLog "S13 batch watcher finished. terminal=$terminalCount"
        break
    }

    Start-Sleep -Seconds 30
}
