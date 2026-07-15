#!/usr/bin/env python3
"""Render the visual adoption decision for the completed Stage 20 v2 pilot."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw

from render_stage20_hypothetical_routing_preview import font


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="docs/visuals/stage20-physical-pilot-v2-result-decision.jpg")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    result_root = root / "docs/results/stage20-physical-pilot-v2-29396657600"
    map_names = ["pilot-estuary.jpg", "pilot-barrage.jpg", "pilot-confluence.jpg", "pilot-fishway.jpg"]

    canvas = Image.new("RGB", (1300, 4180), (243, 247, 248))
    draw = ImageDraw.Draw(canvas)
    ink = (22, 47, 59)
    muted = (65, 88, 100)
    blue = (16, 112, 174)
    green = (28, 130, 72)
    red = (155, 51, 42)

    draw.text((50, 34), "Stage 20　1条件×物理10分パイロット結果", font=font(39, True), fill=ink)
    draw.text((50, 94), "600.0049秒到達／81,861 step／wall 24分52.6秒", font=font(25), fill=muted)
    draw.text((50, 137), "CFL 0.12　質量誤差 2.20e−14　NaN 0　負水深 0　checkpoint 10/10", font=font(24, True), fill=green)
    draw.text((50, 178), "推論入力の一回限り結果。観測検証済み・物理Validation済みではない。", font=font(20, True), fill=red)

    y = 230
    target_width = 1200
    target_height = 864
    for name in map_names:
        image = Image.open(result_root / "maps" / name).convert("RGB")
        image.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
        x = (canvas.width - image.width) // 2
        canvas.paste(image, (x, y))
        y += image.height + 22

    draw.rounded_rectangle((50, 3850, 1250, 4125), radius=18, fill=(230, 243, 247), outline=blue, width=3)
    draw.text((82, 3880), "判断：この4地点の流向表示を基準表示として採用するか", font=font(29, True), fill=ink)
    draw.text((82, 3940), "A　採用し、36時間応答基底の事前計算計画へ進む", font=font(25, True), fill=ink)
    draw.text((82, 3993), "B　採用せず、入力条件・流向・表示方法を見直す", font=font(25, True), fill=ink)
    draw.text((82, 4050), "Aは追加の物理計算を自動承認しません。次の実行範囲は別途提示します。", font=font(19), fill=muted)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=78, optimize=True, progressive=True)
    print(f"{output.relative_to(root)}\t{sha256(output)}\t{output.stat().st_size}")


if __name__ == "__main__":
    main()
