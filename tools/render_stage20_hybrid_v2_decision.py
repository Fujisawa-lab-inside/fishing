#!/usr/bin/env python3
"""Render the Stage 20 hybrid browser mesh-v2 adoption decision sheet."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
        if bold
        else "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def fit(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[Image.Image, tuple[int, int]]:
    x0, y0, x1, y1 = box
    copy = image.copy()
    copy.thumbnail((x1 - x0, y1 - y0), Image.Resampling.LANCZOS)
    return copy, (x0 + (x1 - x0 - copy.width) // 2, y0 + (y1 - y0 - copy.height) // 2)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="docs/visuals/stage20-hybrid-v2-decision.jpg")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()

    browser = Image.open(root / "docs/visuals/stage20-hybrid-v2-browser-screen.png").convert("RGB")
    view_paths = [
        root / "docs/visuals/stage20-hybrid-v2-estuary.jpg",
        root / "docs/visuals/stage20-hybrid-v2-barrage.jpg",
        root / "docs/visuals/stage20-hybrid-v2-confluence.jpg",
        root / "docs/visuals/stage20-hybrid-v2-fishway.jpg",
    ]
    views = [Image.open(path).convert("RGB") for path in view_paths]

    canvas = Image.new("RGB", (2200, 2780), (243, 247, 248))
    draw = ImageDraw.Draw(canvas)
    ink = (22, 47, 59)
    muted = (67, 91, 103)
    blue = (15, 112, 174)
    green = (27, 126, 70)
    line = (195, 208, 214)

    draw.text((60, 38), "Stage 20　36時間ブラウザ経路をメッシュv2へ移行", font=font(48, True), fill=ink)
    draw.text((60, 103), "過去12時間＋未来24時間／1時間間隔37時点／表示経路確認用の合成応答パック", font=font(25), fill=muted)

    draw.rounded_rectangle((50, 150, 1030, 960), radius=18, fill=(255, 255, 255), outline=line, width=2)
    browser_fit, browser_xy = fit(browser, (70, 170, 1010, 940))
    canvas.paste(browser_fit, browser_xy)

    draw.rounded_rectangle((1060, 150, 2150, 960), radius=18, fill=(255, 255, 255), outline=line, width=2)
    draw.text((1110, 198), "実WebKit画面　合格", font=font(34, True), fill=green)
    metrics = [
        ("メッシュ", "v2／50,199セル／68堰面"),
        ("時間範囲", "−12〜＋24時間／37時点"),
        ("合成時間", "375 ms"),
        ("初回読込込み", "395 ms"),
        ("応答パック", "3.4 MiB"),
        ("37時点出力", "21.3 MiB"),
        ("異常値", "0"),
    ]
    y = 285
    for label, value in metrics:
        draw.text((1110, y), label, font=font(24), fill=muted)
        draw.text((1430, y), value, font=font(27, True), fill=ink)
        y += 72
    draw.rounded_rectangle((1100, 800, 2110, 918), radius=14, fill=(231, 244, 248), outline=blue, width=3)
    draw.text((1140, 827), "開発目標10秒以内に対し、実測0.395秒", font=font(29, True), fill=ink)
    draw.text((1140, 872), "約25倍の時間余裕（この端末・合成パック）", font=font(22), fill=muted)

    positions = [
        (50, 1000, 1080, 1735),
        (1120, 1000, 2150, 1735),
        (50, 1770, 1080, 2505),
        (1120, 1770, 2150, 2505),
    ]
    for image, box in zip(views, positions):
        draw.rounded_rectangle(box, radius=16, fill=(255, 255, 255), outline=line, width=2)
        fitted, position = fit(image, (box[0] + 14, box[1] + 14, box[2] - 14, box[3] - 14))
        canvas.paste(fitted, position)

    draw.rounded_rectangle((50, 2540, 2150, 2725), radius=18, fill=(230, 243, 247), outline=blue, width=3)
    draw.text((90, 2570), "判断すること：メッシュv2の36時間ブラウザ経路を採用するか", font=font(33, True), fill=ink)
    draw.text((90, 2630), "A　採用し、物理事前計算の高速化へ進む（推奨）", font=font(28, True), fill=ink)
    draw.text((1180, 2630), "B　経路または表示を修正する", font=font(28, True), fill=ink)
    draw.text((90, 2682), "地図は合成応答パックの表示確認です。実際の流れ・釣果・安全性の判断には使用できません。", font=font(19), fill=muted)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=88, optimize=True, progressive=True)
    print(json.dumps({
        "status": "awaiting_hybrid_v2_adoption_decision",
        "output": args.output,
        "sha256": sha256(output),
        "question": "adopt_mesh_v2_hybrid_browser_path_or_revise",
        "physicalFlowRun": False,
        "publicSimulatorConnected": False,
        "mainMerged": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
