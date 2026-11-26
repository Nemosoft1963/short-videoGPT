"""S15を一話ずつ生成する。外部動画サービス残高不足時は後続を投入しない。"""
import argparse
import json
import re
import shutil
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend" / "src" / "s15_01_20.md"
TEMPLATE = ROOT / "storage" / "projects" / "20261023_045509_685cc268" / "project.json"
MANIFEST = ROOT / "storage" / "batches" / "s15_all_manifest.json"
EXPORT = ROOT / "storage" / "exports" / "消費税の闇_S15_全20話"
SUMMARY = EXPORT / "生成状況.json"
API = "http://127.0.0.1:18000/api/projects"
HEADING = re.compile(r"^##\s+S15-(\d{2})([^\r\n]*)$", re.MULTILINE)
BALANCE = re.compile(r"insufficient[ _-]*(balance|credit|fund)|quota/billing|billing issue|out of credits|残高不足|クレジット不足|チャージ不足|status_code[^\d]*1008|HTTP 402", re.IGNORECASE)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def episodes() -> list[dict]:
    source = SOURCE.read_text(encoding="utf-8")
    headings = list(HEADING.finditer(source))
    if [match.group(1) for match in headings] != [f"{number:02d}" for number in range(1, 21)]:
        raise ValueError("S15台本は20話連番である必要があります")
    result = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(source)
        section = source[heading.end():end]
        blocks = []
        current = []
        for raw in section.splitlines():
            line = raw.strip()
            if line.startswith("映像："):
                if current:
                    blocks.append("\n".join(current))
                current = [line]
            elif current and line and line != "---" and not line.startswith("#"):
                current.append(line)
        if current:
            blocks.append("\n".join(current))
        title = heading.group(2).strip().strip("「」 ")
        script = "\n\n".join(blocks)
        if len(blocks) < 6 or "ターニャの税金談義.jpg" in script:
            raise ValueError(f"S15-{heading.group(1)}: 台本または開始画像が不正")
        result.append({"number": heading.group(1), "title": title, "script": script})
    return result


def create_project(episode: dict, template: dict) -> str:
    payload = {key: value for key, value in template.items() if key not in {"project_id", "created_at", "updated_at"}}
    number = episode["number"]
    payload.update({
        "title": f"消費税の闇 S15｜#{number}｜{episode['title']}",
        "prompt": f"消費税の闇 S15 #{number}「{episode['title']}」。台本の話者・開始画像・画面・BGM指定に沿って生成する。",
        "script": episode["script"],
        "format": "short_vertical",
        "duration": 60,
        "short_timing_mode": "script",
        "model": "google_omni",
        "tts_engine": "stylebertvits2",
        "bgm": True,
        "bgm_auto": True,
        "bgm_filename": "",
        "logo_filename": "消費税の闇新ヘッダー.jpg",
        "subtitle_position_from_bottom_pct": 24.0,
        "start_frame_engine_overrides": {
            str(index): "google_omni"
            for index, block in enumerate(episode["script"].split("\n\n"), start=1)
            if "[start_frame:" in block
        },
    })
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["project_id"]


def status_of(project_id: str) -> dict:
    path = ROOT / "storage" / "projects" / project_id / "status.json"
    return read_json(path) if path.exists() else {"status": "queued", "message": "状態ファイル待機中"}


def export_path(episode: dict) -> Path:
    safe = re.sub(r'[\\/:*?"<>|]', "_", episode["title"]).strip().rstrip(".")
    return EXPORT / f"S15-{episode['number']}_{safe}.mp4"


def save_summary(manifest: dict, all_episodes: list[dict], halt_reason: str = "") -> None:
    by_number = {entry["number"]: entry for entry in manifest["episodes"]}
    results = []
    for episode in all_episodes:
        entry = by_number.get(episode["number"])
        status = status_of(entry["project_id"]) if entry else {"status": "not_started", "message": "未投入"}
        path = export_path(episode)
        results.append({
            "number": episode["number"],
            "title": episode["title"],
            "project_id": entry["project_id"] if entry else "",
            "status": status.get("status", "unknown"),
            "message": status.get("message", ""),
            "file": path.name if path.is_file() else "",
        })
    write_json(SUMMARY, {
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "output_directory": str(EXPORT),
        "halt_reason": halt_reason,
        "episodes": results,
    })


def run(dry_run: bool, retry_failed: bool = False) -> None:
    all_episodes = episodes()
    template = read_json(TEMPLATE)
    if dry_run:
        for episode in all_episodes:
            print(f"READY S15-{episode['number']} {episode['title']} scenes={episode['script'].count('映像：')}")
        return
    EXPORT.mkdir(parents=True, exist_ok=True)
    manifest = read_json(MANIFEST) if MANIFEST.exists() else {"series": "S15", "template_project_id": template["project_id"], "episodes": []}
    by_number = {entry["number"]: entry for entry in manifest["episodes"]}
    for episode in all_episodes:
        number = episode["number"]
        entry = by_number.get(number)
        if entry:
            saved = read_json(ROOT / "storage" / "projects" / entry["project_id"] / "project.json")
            if saved["script"] != episode["script"]:
                raise ValueError(f"S15-{number}: 登録後に台本が変更されました")
            if retry_failed and status_of(entry["project_id"]).get("status") in {"failed", "cancelled"}:
                previous_id = entry["project_id"]
                entry.setdefault("previous_project_ids", []).append(previous_id)
                entry["project_id"] = create_project(episode, template)
                write_json(MANIFEST, manifest)
                print(f"RETRY S15-{number} {previous_id} -> {entry['project_id']}", flush=True)
            else:
                print(f"RESUME S15-{number} {entry['project_id']}", flush=True)
        else:
            project_id = create_project(episode, template)
            entry = {"number": number, "title": episode["title"], "project_id": project_id}
            manifest["episodes"].append(entry)
            by_number[number] = entry
            write_json(MANIFEST, manifest)
            print(f"START S15-{number} {project_id}", flush=True)
        project_id = entry["project_id"]
        deadline = time.monotonic() + 3 * 60 * 60
        previous = ""
        while True:
            status = status_of(project_id)
            state = status.get("status", "unknown")
            message = status.get("message", "")
            if (state, message) != previous:
                print(f"S15-{number} {state}: {message[:240]}", flush=True)
                previous = (state, message)
            save_summary(manifest, all_episodes)
            if state == "completed":
                final = ROOT / "storage" / "projects" / project_id / "final" / "final.mp4"
                if not final.is_file() or final.stat().st_size < 100_000:
                    raise ValueError(f"S15-{number}: 完成動画が見つかりません")
                shutil.copy2(final, export_path(episode))
                save_summary(manifest, all_episodes)
                print(f"DONE S15-{number} {export_path(episode).name}", flush=True)
                break
            if state in {"failed", "cancelled"}:
                kind = "外部動画サービスの残高不足" if BALANCE.search(message + " " + status.get("error", "")) else f"生成失敗（{state}）"
                reason = f"S15-{number}: {kind}: {message[:300]}"
                save_summary(manifest, all_episodes, reason)
                print(f"HALT {reason}", flush=True)
                return
            if time.monotonic() >= deadline:
                reason = f"S15-{number}: 3時間経過。後続話の投入を停止しました"
                save_summary(manifest, all_episodes, reason)
                print(f"HALT {reason}", flush=True)
                return
            time.sleep(15)
    save_summary(manifest, all_episodes)
    print("ALL DONE S15-01..20", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retry-failed", action="store_true", help="残高補充後、失敗話だけ新規プロジェクトで再試行する")
    args = parser.parse_args()
    run(args.dry_run, args.retry_failed)
