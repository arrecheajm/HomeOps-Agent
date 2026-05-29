#!/usr/bin/env python3
"""Collect sanitized AgentDVR camera evidence.

This script is intended to run on the iSpy/AgentDVR host. It reads local
AgentDVR config, media, database, and log evidence and prints JSON without
including credentials or full stream URLs.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import socket
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse


ROOT_CANDIDATES = (
    "/home/spy/AgentDVR",
    "/opt/AgentDVR",
    "/usr/local/AgentDVR",
)
URI_RE = re.compile(r"\b(?:rtsp|http|https)://[^\s<>'\"]+", re.IGNORECASE)
VIDEO_EXTENSIONS = {".avi", ".mkv", ".mp4", ".mov", ".webm"}


def main() -> int:
    root = find_agentdvr_root()
    media_root = root / "Media"
    cameras = configured_cameras(root, media_root)
    microphones = configured_microphones(root, media_root)
    recordings = recording_database(media_root)
    logs = recent_log_summary(root)

    apply_recording_evidence(cameras, recordings, media_root, logs)
    endpoint_checks = [endpoint_check(camera) for camera in cameras]

    payload = {
        "generated_at": utc_now(),
        "agentdvr_root_present": root.exists(),
        "media_root_present": media_root.exists(),
        "camera_count": len(cameras),
        "microphone_count": len(microphones),
        "media_total_mb": round(path_size_bytes(media_root) / 1024 / 1024, 2),
        "endpoint_checks": endpoint_checks,
        "cameras": sanitize_cameras(cameras),
        "microphones": microphones,
        "recording_database": recordings,
        "recent_log_summary": logs,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def find_agentdvr_root() -> Path:
    env_root = os.environ.get("AGENTDVR_ROOT")
    candidates = [Path(env_root)] if env_root else []
    candidates.extend(Path(item) for item in ROOT_CANDIDATES)
    home = Path("/home")
    if home.exists():
        candidates.extend(home.glob("*/AgentDVR"))
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return Path(ROOT_CANDIDATES[0])


def configured_cameras(root: Path, media_root: Path) -> list[dict[str, object]]:
    cameras: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for element in config_elements(root):
        if local_name(element.tag) != "camera":
            continue
        source_uri = first_uri(element)
        values = descendant_values(element)
        name = first_value(values, "name", "objectname", "displayname")
        object_id = first_value(values, "id", "objectid", "oid")
        if not source_uri or not (name or object_id):
            continue
        if not looks_like_camera(element, values):
            continue
        directory = first_value(values, "directory", "dirname", "folder", "dir")
        if not directory:
            continue
        camera = {
            "id": object_id,
            "name": name or f"Camera {object_id}",
            "directory": directory,
            "directory_present": bool(directory and (media_root / directory).exists()),
            "resolution": resolution(values),
            "record_on_detect": first_value(values, "recordondetect", "recordonmotion"),
            "record_on_alert": first_value(values, "recordonalert"),
            "alerts_active": first_value(values, "alertsenabled", "alertsactive", "alerts"),
            "source_uri_present": True,
            "_source_uri": source_uri,
        }
        key = (str(camera["id"]), str(camera["name"]))
        if key not in seen:
            seen.add(key)
            cameras.append(camera)
    return sorted(cameras, key=lambda item: natural_key(str(item.get("id") or item.get("name") or "")))


def configured_microphones(root: Path, media_root: Path) -> list[dict[str, object]]:
    microphones: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for element in config_elements(root):
        if local_name(element.tag) != "microphone":
            continue
        values = descendant_values(element)
        name = first_value(values, "name", "objectname", "displayname")
        object_id = first_value(values, "id", "objectid", "oid")
        if not (name or object_id) or not looks_like_microphone(element, values):
            continue
        directory = first_value(values, "directory", "dirname", "folder", "dir")
        item = {
            "id": object_id,
            "name": name or f"Microphone {object_id}",
            "directory": directory,
            "directory_present": bool(directory and (media_root / directory).exists()),
            "record_on_detect": first_value(values, "recordondetect", "recordonmotion"),
            "record_on_alert": first_value(values, "recordonalert"),
            "detector_enabled": first_value(values, "detectorenabled", "listen", "enabled"),
        }
        key = (str(item["id"]), str(item["name"]))
        if key not in seen:
            seen.add(key)
            microphones.append(item)
    return sorted(microphones, key=lambda item: natural_key(str(item.get("id") or item.get("name") or "")))


def config_elements(root: Path) -> list[ET.Element]:
    elements: list[ET.Element] = []
    paths = (
        sorted((root / "Media" / "XML").glob("*.xml"))
        + sorted((root / "XML").glob("*.xml"))
        + sorted(root.glob("*.xml"))
    )
    for path in paths:
        try:
            root = parse_xml_file(path)
        except ET.ParseError:
            continue
        elements.extend(list(root.iter()))
    return elements


def parse_xml_file(path: Path) -> ET.Element:
    try:
        return ET.parse(path).getroot()
    except ET.ParseError:
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
        text = re.sub(r'encoding="[^"]+"', 'encoding="utf-8"', text, count=1)
        return ET.fromstring(text)


def descendant_values(element: ET.Element) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for name, raw_value in element.attrib.items():
        value = str(raw_value).strip()
        if value:
            values.setdefault(local_name(name), []).append(value)
    for child in element.iter():
        for name, raw_value in child.attrib.items():
            value = str(raw_value).strip()
            if value:
                values.setdefault(local_name(name), []).append(value)
        text = (child.text or "").strip()
        if not text:
            continue
        values.setdefault(local_name(child.tag), []).append(text)
    return values


def first_value(values: dict[str, list[str]], *names: str) -> str:
    for name in names:
        for value in values.get(name.lower(), []):
            if value:
                return value
    return ""


def first_uri(element: ET.Element) -> str:
    for text in all_text(element):
        match = URI_RE.search(text)
        if match:
            return match.group(0)
    return ""


def looks_like_camera(element: ET.Element, values: dict[str, list[str]]) -> bool:
    joined = " ".join([local_name(element.tag), *values.keys(), *[item for values_list in values.values() for item in values_list[:2]]]).lower()
    return "camera" in joined or "video" in joined or bool(first_uri(element))


def looks_like_microphone(element: ET.Element, values: dict[str, list[str]]) -> bool:
    joined = " ".join([local_name(element.tag), *values.keys(), *[item for values_list in values.values() for item in values_list[:2]]]).lower()
    return "microphone" in joined or "audio" in joined or "mic" in joined


def resolution(values: dict[str, list[str]]) -> str:
    existing = first_value(values, "resolution")
    if existing:
        return existing
    width = first_value(values, "width", "resizewidth")
    height = first_value(values, "height", "resizeheight")
    return f"{width}x{height}" if width and height else ""


def recording_database(media_root: Path) -> dict[str, object]:
    db_paths = [
        path
        for path in media_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".db", ".db3", ".sqlite", ".sqlite3"}
    ][:12]
    result: dict[str, object] = {
        "file_records": 0,
        "alert_records": 0,
        "files_by_object": [],
    }
    files_by_object: dict[tuple[int, int], dict[str, object]] = {}
    for db_path in db_paths:
        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
                for table in sqlite_tables(db):
                    lower = table.lower()
                    count = table_count(db, table)
                    if "file" in lower:
                        result["file_records"] = int(result["file_records"]) + count
                        merge_file_groups(files_by_object, db, table)
                    if "alert" in lower:
                        result["alert_records"] = int(result["alert_records"]) + count
        except sqlite3.Error:
            continue
    result["files_by_object"] = sorted(
        files_by_object.values(),
        key=lambda item: (int(item.get("object_type_id") or 0), int(item.get("object_id") or 0)),
    )
    return result


def sqlite_tables(db: sqlite3.Connection) -> list[str]:
    rows = db.execute("select name from sqlite_master where type='table'").fetchall()
    return [str(row[0]) for row in rows]


def table_count(db: sqlite3.Connection, table: str) -> int:
    try:
        row = db.execute(f'select count(*) from "{table}"').fetchone()
    except sqlite3.Error:
        return 0
    return int(row[0] or 0) if row else 0


def merge_file_groups(groups: dict[tuple[int, int], dict[str, object]], db: sqlite3.Connection, table: str) -> None:
    columns = table_columns(db, table)
    object_col = first_column(columns, "objectid", "object_id")
    type_col = first_column(columns, "objecttypeid", "object_type_id", "objecttype")
    size_col = first_column(columns, "sizebytes", "filesize", "size")
    duration_col = first_column(columns, "duration", "durationseconds")
    date_col = first_column(
        columns,
        "created",
        "createdutc",
        "createddate",
        "datecreated",
        "createddateticksutc",
        "starttime",
    )
    if not object_col:
        return
    select_parts = [
        f'"{object_col}"',
        f'"{type_col}"' if type_col else "0",
        "count(*)",
        f"coalesce(sum(\"{size_col}\"), 0)" if size_col else "0",
        f"coalesce(sum(\"{duration_col}\"), 0)" if duration_col else "0",
        f"max(\"{date_col}\")" if date_col else "''",
    ]
    try:
        rows = db.execute(
            f'select {", ".join(select_parts)} from "{table}" group by "{object_col}", 2'
        ).fetchall()
    except sqlite3.Error:
        return
    for row in rows:
        object_id = safe_int(row[0])
        object_type_id = safe_int(row[1])
        key = (object_type_id, object_id)
        existing = groups.setdefault(
            key,
            {
                "object_id": object_id,
                "object_type_id": object_type_id,
                "file_count": 0,
                "total_bytes": 0,
                "total_duration_seconds": 0.0,
                "newest_file_utc": "",
            },
        )
        existing["file_count"] = int(existing["file_count"]) + safe_int(row[2])
        existing["total_bytes"] = int(existing["total_bytes"]) + safe_int(row[3])
        existing["total_duration_seconds"] = round(float(existing["total_duration_seconds"]) + safe_float(row[4]), 2)
        newest = normalize_time(row[5])
        if newest > str(existing["newest_file_utc"]):
            existing["newest_file_utc"] = newest


def table_columns(db: sqlite3.Connection, table: str) -> list[str]:
    try:
        rows = db.execute(f'pragma table_info("{table}")').fetchall()
    except sqlite3.Error:
        return []
    return [str(row[1]) for row in rows]


def first_column(columns: list[str], *names: str) -> str:
    by_normalized = {normalize_name(column): column for column in columns}
    for name in names:
        if name in by_normalized:
            return by_normalized[name]
    return ""


def apply_recording_evidence(
    cameras: list[dict[str, object]],
    recordings: dict[str, object],
    media_root: Path,
    logs: dict[str, dict[str, object]],
) -> None:
    by_object = {
        str(item.get("object_id")): item
        for item in recordings.get("files_by_object", [])
        if isinstance(item, dict)
    }
    for camera in cameras:
        object_id = str(camera.get("id") or "")
        group = by_object.get(object_id, {})
        directory = str(camera.get("directory") or "")
        directory_stats = media_directory_stats(media_root / directory) if directory else {}
        log_summary = logs.get(object_id) or logs.get(str(camera.get("name") or "")) or {}
        camera["recording_file_count"] = int(group.get("file_count") or directory_stats.get("file_count") or 0)
        camera["newest_recording_utc"] = str(group.get("newest_file_utc") or directory_stats.get("newest_recording_utc") or "")
        camera["recording_total_mb"] = round(int(group.get("total_bytes") or directory_stats.get("total_bytes") or 0) / 1024 / 1024, 2)
        camera["recording_event_count"] = int(log_summary.get("recording_event_count") or 0)
        camera["recent_error_count"] = int(log_summary.get("recent_error_count") or 0)
        camera["recent_exception_count"] = int(log_summary.get("recent_exception_count") or 0)
        camera["recent_log_diagnosis"] = str(log_summary.get("diagnosis") or "")


def media_directory_stats(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    files = [item for item in path.rglob("*") if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS]
    newest = max((item.stat().st_mtime for item in files), default=0)
    return {
        "file_count": len(files),
        "total_bytes": sum(item.stat().st_size for item in files),
        "newest_recording_utc": timestamp(newest) if newest else "",
    }


def recent_log_summary(root: Path) -> dict[str, dict[str, object]]:
    lines = recent_log_lines(root)
    summaries: dict[str, dict[str, object]] = {}
    for line in lines:
        camera_key = camera_key_from_line(line)
        if not camera_key:
            continue
        item = summaries.setdefault(
            camera_key,
            {
                "recent_error_count": 0,
                "recent_exception_count": 0,
                "recording_event_count": 0,
                "reconnects_observed": False,
                "representative_error": "",
                "diagnosis": "",
            },
        )
        lower = line.lower()
        if "error" in lower or "open_input" in lower or "connection refused" in lower:
            item["recent_error_count"] = int(item["recent_error_count"]) + 1
            if not item["representative_error"]:
                item["representative_error"] = "OPEN_INPUT: Connection refused" if "connection refused" in lower else line[-160:]
        if "exception" in lower:
            item["recent_exception_count"] = int(item["recent_exception_count"]) + 1
        if "record" in lower and any(token in lower for token in ("open", "created", "closed", "start", "stop")):
            item["recording_event_count"] = int(item["recording_event_count"]) + 1
        if "reconnect" in lower:
            item["reconnects_observed"] = True
    for key, item in summaries.items():
        if "connection refused" in str(item.get("representative_error", "")).lower():
            item["diagnosis"] = f"{camera_label(key)} stream input is being refused before recording can start."
        elif int(item.get("recording_event_count") or 0) > 0:
            item["diagnosis"] = f"{camera_label(key)} is producing recording events."
    return summaries


def recent_log_lines(root: Path, limit: int = 4000) -> list[str]:
    candidates = []
    for directory in (
        root / "Logs",
        root / "Media" / "Logs",
        root / "Media" / "logs",
        root / "Media",
        root,
    ):
        if directory.exists():
            candidates.extend(path for path in directory.glob("*.log") if path.is_file())
            candidates.extend(path for path in directory.glob("log_*.json") if path.is_file())
    lines: list[str] = []
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[:8]:
        try:
            file_lines = read_log_lines(path)
        except OSError:
            continue
        lines.extend(file_lines[-limit:])
    return lines[-limit:]


def read_log_lines(path: Path) -> list[str]:
    if path.suffix.lower() == ".json":
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text.splitlines()
        if isinstance(payload, list):
            return [
                str(item.get("Entry") or item.get("entry") or item)
                for item in payload
                if isinstance(item, dict) or item
            ]
        if isinstance(payload, dict):
            items = payload.get("Logs") or payload.get("logs") or payload.get("items")
            if isinstance(items, list):
                return [
                    str(item.get("Entry") or item.get("entry") or item)
                    for item in items
                    if isinstance(item, dict) or item
                ]
        return text.splitlines()
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def camera_key_from_line(line: str) -> str:
    match = re.search(r"camera\s*(\d+)", line, re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def endpoint_check(camera: dict[str, object]) -> dict[str, object]:
    uri = str(camera.get("_source_uri") or "")
    parsed = urlparse(uri)
    host = parsed.hostname or ""
    port = parsed.port or (554 if parsed.scheme == "rtsp" else 80)
    path_label = parsed.path or ""
    result = {
        "camera": str(camera.get("name") or ""),
        "host_last_octet": host.split(".")[-1] if re.fullmatch(r"\d+(?:\.\d+){3}", host) else "",
        "protocol": parsed.scheme,
        "port": port,
        "path_label": path_label,
        "tcp_reachable": False,
        "tcp_error": "",
        "rtsp_options_status": "",
    }
    if not host:
        result["tcp_error"] = "missing host"
        return result
    try:
        with socket.create_connection((host, port), timeout=2) as sock:
            result["tcp_reachable"] = True
            if parsed.scheme == "rtsp":
                target = f"rtsp://{host}:{port}{path_label or '/'}"
                sock.sendall(f"OPTIONS {target} RTSP/1.0\r\nCSeq: 1\r\n\r\n".encode("ascii"))
                first_line = sock.recv(160).decode("utf-8", errors="replace").splitlines()
                result["rtsp_options_status"] = first_line[0] if first_line else ""
    except OSError as exc:
        result["tcp_error"] = f"{exc.__class__.__name__}: {exc}"
    return result


def sanitize_cameras(cameras: list[dict[str, object]]) -> list[dict[str, object]]:
    sanitized = []
    for camera in cameras:
        item = dict(camera)
        item.pop("_source_uri", None)
        sanitized.append(item)
    return sanitized


def path_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def all_text(element: ET.Element) -> list[str]:
    values: list[str] = []
    for item in element.iter():
        values.extend(str(value).strip() for value in item.attrib.values() if str(value).strip())
        text = (item.text or "").strip()
        if text:
            values.append(text)
    return values


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def natural_key(value: str) -> tuple[int, str]:
    return (safe_int(value), value)


def safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def safe_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def normalize_time(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    if text.isdigit():
        numeric = int(text)
        if numeric > 10_000_000_000_000:
            return timestamp((numeric - 621_355_968_000_000_000) / 10_000_000)
        return timestamp(float(numeric))
    return text.replace(" ", "T").replace("+00:00", "Z")


def timestamp(value: float) -> str:
    return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def camera_label(key: str) -> str:
    return key if key.lower().startswith("camera") else f"Camera {key}"


if __name__ == "__main__":
    raise SystemExit(main())
