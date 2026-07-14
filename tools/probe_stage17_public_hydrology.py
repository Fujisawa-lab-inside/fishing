#!/usr/bin/env python3
"""Probe only public official hydrology pages and record reproducible diagnostics.

This script does not assign any station to a model boundary and does not transform
or ingest observations into the physical solver.  It records HTTP metadata，page
hashes，discovered script URLs，and candidate API strings for later human review.
"""

from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

USER_AGENT = (
    "OngaStage17PublicSourceProbe/1.0 "
    "(+https://github.com/Fujisawa-lab-inside/fishing; research metadata audit)"
)
MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_SCRIPT_COUNT = 40
MAX_SCRIPT_BYTES = 8 * 1024 * 1024
ALLOWED_HOSTS = frozenset({
    "www.qsr.mlit.go.jp",
    "www.river.go.jp",
    "www1.river.go.jp",
    "www.data.jma.go.jp",
})

TARGETS = [
    {
        "id": "onga_office_home",
        "url": "https://www.qsr.mlit.go.jp/onga/",
        "role": "official office and contact",
    },
    {
        "id": "onga_office_contact",
        "url": "https://www.qsr.mlit.go.jp/onga/access/index.html",
        "role": "official postal, telephone, fax, and email contact route",
    },
    {
        "id": "onga_hydrology_portal",
        "url": "https://www.qsr.mlit.go.jp/onga/river_info/quality.html",
        "role": "official hydrology database links",
    },
    {
        "id": "onga_realtime_station_list",
        "url": "https://www.qsr.mlit.go.jp/onga/disaster/rt/realtime_suii.html",
        "role": "official station list",
    },
    {
        "id": "station_gion_bridge",
        "url": "https://www.river.go.jp/kawabou/pc/tm?ofcCd=22806&itmkndCd=004&obsCd=00020",
        "role": "Nishikawa candidate station",
    },
    {
        "id": "station_karakuma",
        "url": "https://www.river.go.jp/kawabou/pc/tm?ofcCd=22806&itmkndCd=004&obsCd=00005",
        "role": "Onga main-stem candidate station",
    },
    {
        "id": "station_nakama",
        "url": "https://www.river.go.jp/kawabou/pc/tm?ofcCd=22806&itmkndCd=004&obsCd=00006",
        "role": "Onga main-stem candidate station",
    },
    {
        "id": "station_tateyashiki",
        "url": "https://www.qsr.mlit.go.jp/onga/onga_wlevel/tateyashiki_graph.php",
        "role": "lower Onga candidate station",
    },
    {
        "id": "mlit_hydrology_database",
        "url": "https://www1.river.go.jp/",
        "role": "national historical hydrology database",
    },
    {
        "id": "jma_tide_table",
        "url": "https://www.data.jma.go.jp/kaiyou/db/tide/suisan/index.php",
        "role": "secondary astronomical-tide reference",
    },
]


class ResourceParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[str] = []
        self.links: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag.lower() == "script" and values.get("src"):
            self.scripts.append(str(values["src"]))
        if tag.lower() == "a" and values.get("href"):
            self.links.append(str(values["href"]))
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join(part.strip() for part in self.title_parts if part.strip())


def require_allowed_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
        raise ValueError(f"URL is outside the official-source allowlist: {url}")
    return url


class AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        require_allowed_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(
    AllowlistedRedirectHandler(),
    urllib.request.HTTPSHandler(context=ssl.create_default_context()),
)


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str | None
    status: int | None
    headers: dict[str, str]
    body: bytes
    elapsed_seconds: float
    error: str | None

    @property
    def sha256(self) -> str | None:
        return hashlib.sha256(self.body).hexdigest() if self.body else None


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "resource"


def fetch(url: str, timeout: float = 30.0, max_bytes: int = MAX_BODY_BYTES) -> FetchResult:
    require_allowed_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json,text/javascript,*/*;q=0.8",
            "Accept-Language": "ja,en;q=0.7",
        },
    )
    started = time.perf_counter()
    try:
        with OPENER.open(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                body = body[:max_bytes]
            return FetchResult(
                requested_url=url,
                final_url=response.geturl(),
                status=int(getattr(response, "status", response.getcode())),
                headers={key.lower(): value for key, value in response.headers.items()},
                body=body,
                elapsed_seconds=time.perf_counter() - started,
                error=None,
            )
    except Exception as error:  # diagnostic probe must preserve the failure
        status = error.code if isinstance(error, urllib.error.HTTPError) else None
        body = b""
        if isinstance(error, urllib.error.HTTPError):
            try:
                body = error.read(max_bytes)
            except Exception:
                body = b""
        return FetchResult(
            requested_url=url,
            final_url=getattr(error, "url", None),
            status=int(status) if status is not None else None,
            headers={},
            body=body,
            elapsed_seconds=time.perf_counter() - started,
            error=f"{type(error).__name__}: {error}",
        )


def decode_text(body: bytes, content_type: str | None) -> tuple[str, str]:
    candidates: list[str] = []
    if content_type:
        match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type, re.I)
        if match:
            candidates.append(match.group(1))
    head = body[:4096].decode("ascii", errors="ignore")
    match = re.search(r"charset\s*=\s*[\"']?([A-Za-z0-9._-]+)", head, re.I)
    if match:
        candidates.append(match.group(1))
    candidates.extend(["utf-8", "cp932", "shift_jis", "euc_jp"])
    for encoding in candidates:
        try:
            return body.decode(encoding), encoding
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace"), "utf-8-replace"


def extract_candidate_strings(text: str) -> list[str]:
    patterns = [
        r"https?://[^\"'\s)]+",
        r"[\"'](/[^\"']*(?:api|observ|water|suii|river|kawabou|telemetry)[^\"']*)[\"']",
        r"[\"']([^\"']*(?:obsCd|obsrvId|ofcCd|itmkndCd)[^\"']*)[\"']",
    ]
    values: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            value = match.group(1) if match.lastindex else match.group(0)
            value = value.strip()
            if 3 <= len(value) <= 600:
                values.add(value)
    return sorted(values)[:500]


def normalise_urls(base_url: str, references: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for reference in references:
        url = urllib.parse.urljoin(base_url, reference)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS:
            continue
        if url in seen:
            continue
        seen.add(url)
        result.append(url)
    return result


def serialise_fetch(result: FetchResult) -> dict[str, object]:
    return {
        "requestedUrl": result.requested_url,
        "finalUrl": result.final_url,
        "status": result.status,
        "contentType": result.headers.get("content-type"),
        "contentLengthHeader": result.headers.get("content-length"),
        "receivedBytes": len(result.body),
        "sha256": result.sha256,
        "elapsedSeconds": round(result.elapsed_seconds, 6),
        "error": result.error,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="stage17-public-hydrology-probe")
    arguments = parser.parse_args()
    output = Path(arguments.output)
    pages_dir = output / "pages"
    scripts_dir = output / "scripts"
    pages_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    target_reports: list[dict[str, object]] = []
    script_queue: list[tuple[str, str]] = []
    for target in TARGETS:
        result = fetch(target["url"])
        report: dict[str, object] = {
            "id": target["id"],
            "role": target["role"],
            **serialise_fetch(result),
            "title": None,
            "encoding": None,
            "scriptUrls": [],
            "linkCount": 0,
            "candidateStrings": [],
        }
        if result.body:
            text, encoding = decode_text(result.body, result.headers.get("content-type"))
            suffix = ".html" if "html" in (result.headers.get("content-type") or "").lower() else ".txt"
            (pages_dir / f"{safe_name(str(target['id']))}{suffix}").write_text(text, encoding="utf-8")
            resource_parser = ResourceParser()
            try:
                resource_parser.feed(text)
            except Exception as error:
                report["parserError"] = f"{type(error).__name__}: {error}"
            base = result.final_url or target["url"]
            scripts = normalise_urls(base, resource_parser.scripts)
            report["title"] = resource_parser.title or None
            report["encoding"] = encoding
            report["scriptUrls"] = scripts
            report["linkCount"] = len(resource_parser.links)
            report["candidateStrings"] = extract_candidate_strings(text)
            for script_url in scripts:
                script_queue.append((str(target["id"]), script_url))
        target_reports.append(report)

    script_reports: list[dict[str, object]] = []
    seen_scripts: set[str] = set()
    for parent_id, script_url in script_queue:
        if script_url in seen_scripts or len(seen_scripts) >= MAX_SCRIPT_COUNT:
            continue
        seen_scripts.add(script_url)
        result = fetch(script_url, max_bytes=MAX_SCRIPT_BYTES)
        report = {
            "parentTargetId": parent_id,
            **serialise_fetch(result),
            "candidateStrings": [],
        }
        if result.body:
            text, encoding = decode_text(result.body, result.headers.get("content-type"))
            name = f"{len(script_reports):03d}_{safe_name(urllib.parse.urlparse(script_url).path)}.js"
            (scripts_dir / name).write_text(text, encoding="utf-8")
            report["savedAs"] = str(Path("scripts") / name)
            report["encoding"] = encoding
            report["candidateStrings"] = extract_candidate_strings(text)
        script_reports.append(report)

    target_by_id = {item["id"]: item for item in target_reports}
    required_reachable = [
        "onga_office_home",
        "onga_office_contact",
        "onga_hydrology_portal",
        "onga_realtime_station_list",
        "station_tateyashiki",
        "jma_tide_table",
    ]
    required_failures = [
        target_id for target_id in required_reachable
        if target_by_id[target_id]["status"] != 200
    ]
    station_page_statuses = {
        target_id: target_by_id[target_id]["status"]
        for target_id in ["station_gion_bridge", "station_karakuma", "station_nakama"]
    }
    discovered_candidates = sorted({
        value
        for report in [*target_reports, *script_reports]
        for value in report.get("candidateStrings", [])
    })
    final_report = {
        "schema": "onga-stage17-public-hydrology-probe-v1",
        "status": "passed" if not required_failures else "partial",
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "targets": target_reports,
        "scripts": script_reports,
        "diagnostics": {
            "allowedHosts": sorted(ALLOWED_HOSTS),
            "requiredReachabilityFailures": required_failures,
            "stationPageStatuses": station_page_statuses,
            "discoveredScriptCount": len(script_reports),
            "discoveredCandidateStringCount": len(discovered_candidates),
            "discoveredCandidateStrings": discovered_candidates,
        },
        "interpretationLimits": [
            "HTTP reachability does not prove that a station supplies discharge or historical data.",
            "No station is assigned to model boundaries M，N，O，or G by this probe.",
            "No downloaded value is approved as a physical model input.",
            "Astronomical tide predictions remain separate from observed river water level.",
        ],
        "safeguards": {
            "approvedWaterGeometryChanged": False,
            "physicalValuesAssigned": False,
            "externalContactPerformed": False,
            "publicSimulatorConnected": False,
            "calibrationPerformed": False,
        },
    }
    (output / "report.json").write_text(
        json.dumps(final_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": final_report["status"],
        "requiredReachabilityFailures": required_failures,
        "stationPageStatuses": station_page_statuses,
        "discoveredScriptCount": len(script_reports),
        "discoveredCandidateStringCount": len(discovered_candidates),
        "output": str(output / "report.json"),
    }, ensure_ascii=False, indent=2))
    if required_failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
