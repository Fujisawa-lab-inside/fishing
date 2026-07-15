#!/usr/bin/env python3
"""Render the browser mesh v2 creation result and connection decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc" if bold else "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/NotoSansGothic-Regular.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    copy = image.copy()
    copy.thumbnail(size, Image.Resampling.LANCZOS)
    return copy


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--v1-validation", default="config/stage20_browser_reference_validation_v1.json")
    parser.add_argument("--v2-validation", default="config/stage20_browser_mesh_v2_validation_v1.json")
    parser.add_argument("--v2-manifest", default="public/data/onga/stage20/mesh-v2.json")
    parser.add_argument("--overview", default="docs/visuals/stage20-estuary-overview-v2.png")
    parser.add_argument("--endpoint-result", default="docs/visuals/stage20-endpoint-mesh-linux-result-v1.png")
    parser.add_argument("--output", default="docs/visuals/stage20-browser-mesh-v2-decision.png")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    v1 = json.loads((root / args.v1_validation).read_text(encoding="utf-8"))
    v2 = json.loads((root / args.v2_validation).read_text(encoding="utf-8"))
    manifest_path = root / args.v2_manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    binary_path = manifest_path.parent / manifest["binary"]["url"]
    assert v2["status"] == "passed_not_connected"
    assert manifest["schema"] == "onga-stage20-browser-mesh-v2"
    assert sha256(binary_path) == manifest["binary"]["sha256"]

    v1_dt = float(v1["syntheticStillWaterValidation"]["adaptiveStepSeconds"])
    v2_dt = float(v2["syntheticStillWaterValidation"]["adaptiveStepSeconds"])
    ratio = v2_dt / v1_dt
    overview = Image.open(root / args.overview).convert("RGB")
    endpoint = Image.open(root / args.endpoint_result).convert("RGB")
    map_crop = overview.crop((225, 215, 1375, 1020))
    scale_x = endpoint.width / 1600
    scale_y = endpoint.height / 1135
    candidate_boxes = [
        (50, 625, 775, 955),
        (825, 625, 1550, 955),
    ]
    endpoint_crops = [
        endpoint.crop(tuple(round(value * (scale_x if index % 2 == 0 else scale_y)) for index, value in enumerate(box)))
        for box in candidate_boxes
    ]

    canvas = Image.new("RGB", (1800, 1400), (244, 247, 248))
    draw = ImageDraw.Draw(canvas)
    ink = (23, 49, 61)
    muted = (72, 98, 111)
    border = (199, 211, 216)
    green = (20, 122, 91)
    blue = (0, 137, 208)
    draw.text((55, 35), "ブラウザ用メッシュv2を作成しました", font=font(43, True), fill=ink)
    draw.text((55, 93), "正式候補をブラウザ配列へ変換し、v1互換性とv2静水保存を確認", font=font(22), fill=muted)

    draw.rounded_rectangle((50, 130, 1750, 230), radius=18, fill=(255, 255, 255), outline=border, width=2)
    metrics = [
        (80, "50,199セル", "河口全域・両端補正済み"),
        (620, f"時間刻み {ratio:.1f}倍", f"{v1_dt:.6f} → {v2_dt:.6f} 秒"),
        (1190, "v1回帰・v2検証 合格", "非有限値0・セル補正0"),
    ]
    for x, value, note in metrics:
        draw.text((x, 153), value, font=font(25, True), fill=ink)
        draw.text((x, 193), note, font=font(18), fill=muted)

    map_panel = map_crop.resize((1180, 826), Image.Resampling.LANCZOS)
    canvas.paste(map_panel, (50, 260))
    draw.rectangle((50, 260, 1230, 1086), outline=border, width=2)
    draw.text((75, 280), "ブラウザv2・河口全域", font=font(24, True), fill=(255, 255, 255), stroke_width=4, stroke_fill=ink)

    draw.text((1280, 270), "河口堰の両端", font=font(25, True), fill=ink)
    y_positions = (315, 555)
    for crop, y in zip(endpoint_crops, y_positions):
        panel = fit(crop, (470, 215))
        canvas.paste(panel, (1280, y))
        draw.rectangle((1280, y, 1280 + panel.width, y + panel.height), outline=border, width=2)

    draw.rounded_rectangle((1280, 800, 1750, 1086), radius=18, fill=(255, 255, 255), outline=border, width=2)
    draw.text((1310, 830), "静水試験の時間刻み", font=font(22, True), fill=ink)
    bar_x, bar_w = 1320, 375
    draw.text((1310, 880), "v1", font=font(19, True), fill=muted)
    draw.rectangle((bar_x + 55, 883, bar_x + 55 + max(8, round(bar_w / ratio)), 908), fill=(151, 169, 177))
    draw.text((1310, 935), "v2", font=font(19, True), fill=ink)
    draw.rectangle((bar_x + 55, 938, bar_x + 55 + bar_w, 963), fill=green)
    draw.text((1310, 990), f"最小セル面積 0.0021 → 0.506 m²", font=font(18), fill=muted)
    draw.text((1310, 1030), "現行v1ファイルは保持", font=font(18), fill=muted)

    draw.rounded_rectangle((50, 1120, 1750, 1300), radius=18, fill=(230, 242, 246), outline=blue, width=3)
    draw.text((82, 1150), "判断すること：作業ブランチのブラウザ参照をv2へ接続するか", font=font(28, True), fill=ink)
    draw.text((82, 1210), "A　v2へ接続して画面動作を確認する（推奨）", font=font(24, True), fill=ink)
    draw.text((1040, 1210), "B　接続前に修正する", font=font(24, True), fill=ink)
    draw.text((82, 1260), "接続してもmain反映・公開・物理計算は行いません", font=font(18), fill=muted)
    draw.text((55, 1340), "全域の色と矢印は表示確認用の合成場です。流れの物理計算結果ではありません。背景：国土地理院", font=font(18), fill=muted)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=True)
    record = {
        "schema": "onga-stage20-browser-mesh-v2-decision-visual-v1",
        "status": "awaiting_reference_connection_decision",
        "output": str(output.relative_to(root)),
        "pngSha256": sha256(output),
        "meshBinarySha256": manifest["binary"]["sha256"],
        "meshManifestSha256": sha256(manifest_path),
        "cells": manifest["counts"]["cells"],
        "syntheticTimeStepV1Seconds": v1_dt,
        "syntheticTimeStepV2Seconds": v2_dt,
        "syntheticTimeStepRatio": ratio,
        "physicalFlowRun": False,
        "publicSimulatorConnected": False,
    }
    output.with_suffix(".json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
