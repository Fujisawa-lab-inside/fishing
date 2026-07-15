#!/usr/bin/env python3
"""Render the S01 numerical result and the exact next-segment decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from render_stage20_hypothetical_routing_preview import font


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fit_image(path: Path, size: tuple[int, int]) -> Image.Image:
    image = Image.open(path).convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, (231, 237, 240))
    x = (size[0] - image.width) // 2
    y = (size[1] - image.height) // 2
    canvas.paste(image, (x, y))
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="docs/visuals/stage20-reference-s01-result-decision.jpg")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    result = json.loads((root / "config/stage20_reference_s01_canary_result_v1.json").read_text(encoding="utf-8"))
    analysis = json.loads((root / "config/stage20_reference_s01_canary_analysis_v1.json").read_text(encoding="utf-8"))
    map_root = root / "docs/results/stage20-reference-s01-canary-29415527789/maps"

    canvas = Image.new("RGB", (1600, 2840), (243, 247, 248))
    draw = ImageDraw.Draw(canvas)
    ink = (22, 47, 59)
    muted = (65, 88, 100)
    blue = (16, 112, 174)
    green = (28, 130, 72)
    orange = (190, 103, 26)
    red = (155, 51, 42)
    white = (255, 255, 255)
    pale_blue = (225, 241, 248)
    pale_green = (225, 244, 232)
    pale_orange = (252, 239, 221)
    grey = (180, 195, 202)

    draw.text((55, 36), "S01実計算結果　次の1区間へ進むか", font=font(42, True), fill=ink)
    draw.text((55, 103), "−24〜−16時間の助走8時間は完了。数値安定性は合格、観測による物理検証ではありません。", font=font(22), fill=muted)

    draw.rounded_rectangle((55, 155, 1545, 405), radius=18, fill=white, outline=grey, width=2)
    metrics = [
        ("到達", "8物理時間", green),
        ("計算時間", "3時間48分", blue),
        ("5時間上限まで", "1時間12分", blue),
        ("checkpoint", "8／8", green),
    ]
    for index, (label, value, color) in enumerate(metrics):
        x = 90 + index * 365
        draw.text((x, 190), label, font=font(18), fill=muted)
        draw.text((x, 230), value, font=font(31, True), fill=color)
    draw.text((90, 305), f"最大CFL {result['numerical']['maximumCfl']:.2f}　　相対質量誤差 {result['numerical']['maximumRelativeMassBalanceError']:.2e}　　非有限値 0　　負水深 0", font=font(23, True), fill=ink)
    draw.text((90, 355), "完全な証拠13ファイルと最終restartのSHA-256を検証済み。自動再実行は停止済み。", font=font(20), fill=muted)

    draw.text((55, 455), "−16時間時点の実計算地図", font=font(30, True), fill=ink)
    draw.text((55, 500), "色と矢印は同じメッシュセル値。表示上限0.118 m/s。", font=font(19), fill=muted)
    map_specs = [
        ("pilot-estuary.jpg", "河口全域"),
        ("pilot-barrage.jpg", "河口堰付近"),
        ("pilot-confluence.jpg", "曲川・遠賀川合流地点"),
        ("pilot-fishway.jpg", "魚道付近"),
    ]
    image_w, image_h = 720, 520
    for index, (name, label) in enumerate(map_specs):
        column = index % 2
        row = index // 2
        x = 55 + column * 765
        y = 550 + row * 585
        draw.rounded_rectangle((x, y, x + 735, y + 555), radius=14, fill=white, outline=grey, width=2)
        draw.text((x + 18, y + 12), label, font=font(21, True), fill=ink)
        thumb = fit_image(map_root / name, (image_w, image_h))
        canvas.paste(thumb, (x + 8, y + 45))

    chart_top = 1745
    draw.rounded_rectangle((55, chart_top, 1545, chart_top + 350), radius=18, fill=white, outline=grey, width=2)
    draw.text((85, chart_top + 25), "8時間の変化（平均流速）", font=font(27, True), fill=ink)
    draw.text((85, chart_top + 70), "潮位境界が時間変化するため、最後の1時間も状態は変化。助走十分とはまだ判定できません。", font=font(19), fill=red)
    values = [float(item["meanSpeedMPS"]) for item in analysis["hourly"]]
    x0, y0, width, height = 130, chart_top + 145, 1320, 145
    ceiling = 0.05
    draw.line((x0, y0 + height, x0 + width, y0 + height), fill=grey, width=2)
    draw.line((x0, y0, x0, y0 + height), fill=grey, width=2)
    points = []
    for index, value in enumerate(values):
        x = x0 + index * width / (len(values) - 1)
        y = y0 + height * (1.0 - min(value, ceiling) / ceiling)
        points.append((x, y))
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=blue)
        draw.text((x - 14, y0 + height + 10), str(index + 1), font=font(16), fill=muted)
    draw.line(points, fill=blue, width=5, joint="curve")
    draw.text((85, y0 - 4), "0.05", font=font(15), fill=muted)
    draw.text((90, y0 + height - 12), "0", font=font(15), fill=muted)
    draw.text((x0 + width - 315, y0 + 12), f"8h平均 {values[-1]:.3f} m/s", font=font(20, True), fill=blue)
    draw.text((x0 + width - 315, y0 + 51), "最終1h RMS変化 0.0435 m/s", font=font(18, True), fill=red)
    draw.text((x0 + width - 315, y0 + 90), "横軸：S01開始後の時間", font=font(16), fill=muted)

    draw.rounded_rectangle((55, 2140, 1545, 2325), radius=18, fill=pale_green, outline=green, width=3)
    draw.text((85, 2167), "準備済みの次区間：reference-s02", font=font(29, True), fill=ink)
    draw.text((85, 2220), "−16→−8時間／同じ基準条件／S01の検証済みrestartから継続", font=font(24, True), fill=green)
    draw.text((85, 2270), "出力：8 checkpoint＋表示対象の最初の5枚（−12, −11, −10, −9, −8h）", font=font(21), fill=ink)

    draw.text((55, 2370), "あなたが判断すること", font=font(30, True), fill=ink)
    draw.rounded_rectangle((55, 2425, 1545, 2605), radius=20, fill=pale_blue, outline=blue, width=4)
    draw.rounded_rectangle((85, 2455, 215, 2513), radius=14, fill=blue)
    draw.text((128, 2465), "A", font=font(28, True), fill=white)
    draw.text((245, 2454), "S02を一回だけ実行する（推奨）", font=font(31, True), fill=ink)
    draw.text((90, 2535), "最大5時間／自動retryなし／残り64区間は停止／main・公開には未反映", font=font(21), fill=ink)
    draw.text((90, 2570), "S01実績3時間48分は目安であり、S02の所要時間保証ではありません。", font=font(18), fill=muted)

    draw.rounded_rectangle((55, 2645, 1545, 2780), radius=20, fill=pale_orange, outline=orange, width=3)
    draw.rounded_rectangle((85, 2675, 215, 2733), radius=14, fill=orange)
    draw.text((128, 2685), "B", font=font(28, True), fill=white)
    draw.text((245, 2675), "S01結果だけを保存し、次の計算をしない", font=font(29, True), fill=ink)
    draw.text((90, 2737), "追加の計算資源と実行リスクは発生しません。", font=font(20), fill=ink)

    draw.text((55, 2800), "返信：A＝S02を一回だけ実行　／　B＝ここで停止", font=font(24, True), fill=ink)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=88, optimize=True, progressive=True)
    print(f"{output.relative_to(root)}\t{sha256(output)}\t{output.stat().st_size}")


if __name__ == "__main__":
    main()
