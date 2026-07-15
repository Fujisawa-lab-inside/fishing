#!/usr/bin/env python3
"""Render the Linux reproduction result and next mesh-adoption decision."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--result",
        default="config/stage20_endpoint_mesh_linux_reproduction_result_v1.json",
    )
    parser.add_argument(
        "--comparison",
        default="docs/visuals/stage20-barrage-endpoint-mesh-decision-v1.svg",
    )
    parser.add_argument(
        "--output",
        default="docs/visuals/stage20-endpoint-mesh-linux-result-v1.svg",
    )
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    result_path = root / args.result
    comparison_path = root / args.comparison
    result = json.loads(result_path.read_text(encoding="utf-8"))
    evidence_path = root / result["evidence"]["path"]
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert result["status"] in {"passed_awaiting_canonical_adoption", "approved_canonical"}
    assert evidence["status"] == "passed"
    assert all(evidence["checks"].values())
    assert sha256(evidence_path) == result["evidence"]["sha256"]
    assert evidence["candidate"]["artifactSha256"] == result["candidate"]["artifactSha256"]

    comparison = base64.b64encode(comparison_path.read_bytes()).decode("ascii")
    short_sha = result["candidate"]["artifactSha256"][:12]
    run_id = result["run"]["id"]
    duration = result["run"]["durationSeconds"]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1135" viewBox="0 0 1600 1135" role="img" aria-labelledby="title desc">
<title id="title">Linux x86で候補メッシュが完全一致</title>
<desc id="desc">河口堰両端の候補メッシュをLinux x86で再生成し、NPZ全体と全12配列が完全一致した結果。正式候補として固定するかを判断する。</desc>
<style>
text{{font-family:"Hiragino Sans","Yu Gothic","Noto Sans CJK JP",sans-serif;fill:#17313d}}
.title{{font-size:42px;font-weight:600}}.sub{{font-size:21px;fill:#48626f}}.pass{{font-size:25px;font-weight:600;fill:#ffffff}}
.metric{{font-size:22px;font-weight:600}}.decision{{font-size:25px;font-weight:600}}.choice{{font-size:23px;font-weight:600}}.small{{font-size:17px;fill:#48626f}}
</style>
<rect width="1600" height="1135" fill="#f4f7f8"/>
<text x="50" y="58" class="title">Linux x86で完全一致しました</text>
<text x="50" y="94" class="sub">GitHub run {run_id}・{duration}秒・幾何生成のみ（物理計算なし）</text>
<rect x="50" y="120" width="1500" height="88" rx="16" fill="#147a5b"/>
<text x="80" y="158" class="pass">✓ SHA-256 完全一致</text>
<text x="575" y="158" class="pass">✓ 全12配列 完全一致</text>
<text x="1110" y="158" class="pass">✓ Linux x86-64</text>
<text x="80" y="190" class="small" style="fill:#ffffff">artifact {short_sha}…</text>
<text x="575" y="190" class="small" style="fill:#ffffff">セル・境界・ゲート・魚道も同一</text>
<text x="1110" y="190" class="small" style="fill:#ffffff">Python {result['platform']['python']}</text>
<clipPath id="comparison-panels"><rect x="50" y="235" width="1500" height="675" rx="14"/></clipPath>
<g clip-path="url(#comparison-panels)">
  <image x="3.125" y="14.688" width="1500" height="1064.063" href="data:image/svg+xml;base64,{comparison}"/>
</g>
<rect x="50" y="235" width="1500" height="675" rx="14" fill="none" stroke="#ffffff" stroke-width="3"/>
<rect x="50" y="935" width="1500" height="130" rx="16" fill="#e6f2f6" stroke="#0089d0" stroke-width="3"/>
<text x="80" y="977" class="decision">判断すること：Linuxで一致した候補を正式候補として固定するか</text>
<text x="80" y="1025" class="choice">A　正式候補として固定し、ブラウザ用メッシュv2を作る（推奨）</text>
<text x="1000" y="1025" class="choice">B　固定せず調査する</text>
<text x="80" y="1105" class="small">この判断ではmain反映・公開・物理計算は行いません</text>
</svg>
'''
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")
    visual_record_path = output.with_suffix(".json")
    existing = (
        json.loads(visual_record_path.read_text(encoding="utf-8"))
        if visual_record_path.is_file()
        else {}
    )
    approval = existing.get("approval")
    visual_record = {
        "schema": "onga-stage20-endpoint-mesh-linux-result-visual-v1",
        "status": (
            "approved_for_browser_mesh_v2"
            if approval
            else "awaiting_canonical_adoption_decision"
        ),
        "svg": str(output.relative_to(root)),
        "svgSha256": sha256(output),
        "sourceComparisonSha256": sha256(comparison_path),
        "resultRecordSha256": sha256(result_path),
        "evidenceSha256": sha256(evidence_path),
        "runId": run_id,
        "artifactSha256": result["candidate"]["artifactSha256"],
    }
    if approval:
        visual_record["approval"] = approval
    visual_record_path.write_text(
        json.dumps(visual_record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(visual_record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
