#!/usr/bin/env python3
"""Render the S02 result and the browser-comparison next decision."""

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
    canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="docs/visuals/stage20-reference-s02-result-decision.jpg")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    analysis = json.loads((root / "config/stage20_reference_s02_analysis_v1.json").read_text(encoding="utf-8"))
    map_root = root / "docs/results/stage20-reference-s02-29434250546/maps"

    canvas = Image.new("RGB", (1600, 3370), (243, 247, 248))
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

    draw.text((55, 36), "S02実計算結果　次は比較検証を作るか", font=font(42, True), fill=ink)
    draw.text((55, 103), "−16〜−8時間を完了。表示対象の最初の5時刻を直接solverから保存しました。", font=font(22), fill=muted)

    draw.rounded_rectangle((55, 155, 1545, 420), radius=18, fill=white, outline=grey, width=2)
    metrics = [
        ("到達", "8物理時間", green),
        ("計算時間", "3時間59分", blue),
        ("5時間上限まで", "1時間01分", blue),
        ("snapshot", "5／5", green),
    ]
    for index, (label, value, color) in enumerate(metrics):
        x = 90 + index * 365
        draw.text((x, 190), label, font=font(18), fill=muted)
        draw.text((x, 230), value, font=font(31, True), fill=color)
    draw.text((90, 310), "最大CFL 0.12　　相対質量誤差 8.64e-14　　非有限値 0　　負水深 0　　checkpoint 8／8", font=font(22, True), fill=ink)
    draw.text((90, 365), "S01→S02 restart連続性と証拠18ファイルのSHA-256を検証済み。", font=font(20), fill=muted)

    draw.text((55, 470), "−12〜−8時間の直接計算結果（全画像0〜0.23 m/sの同一尺度）", font=font(29, True), fill=ink)
    map_specs = [(-12, "hour-12"), (-11, "hour-11"), (-10, "hour-10"), (-9, "hour-9"), (-8, "hour-8")]
    image_w, image_h = 720, 520
    positions = [(55, 525), (820, 525), (55, 1110), (820, 1110), (437, 1695)]
    for (hour, directory), (x, y) in zip(map_specs, positions):
        draw.rounded_rectangle((x, y, x + 735, y + 555), radius=14, fill=white, outline=grey, width=2)
        draw.text((x + 18, y + 12), f"model時刻 {hour}時間", font=font(21, True), fill=ink)
        thumb = fit_image(map_root / directory / "pilot-estuary.jpg", (image_w, image_h))
        canvas.paste(thumb, (x + 8, y + 45))

    chart_top = 2295
    draw.rounded_rectangle((55, chart_top, 1545, chart_top + 330), radius=18, fill=white, outline=grey, width=2)
    draw.text((85, chart_top + 25), "5時刻の河口全セル平均流速", font=font(27, True), fill=ink)
    snapshots = analysis["snapshots"]
    values = [float(item["meanSpeedMPS"]) for item in snapshots]
    x0, y0, width, height = 145, chart_top + 115, 1260, 130
    ceiling = 0.065
    draw.line((x0, y0 + height, x0 + width, y0 + height), fill=grey, width=2)
    draw.line((x0, y0, x0, y0 + height), fill=grey, width=2)
    points = []
    for index, (item, value) in enumerate(zip(snapshots, values)):
        x = x0 + index * width / (len(values) - 1)
        y = y0 + height * (1.0 - value / ceiling)
        points.append((x, y))
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=blue)
        draw.text((x - 28, y0 + height + 12), f"{item['modelHour']}h", font=font(17), fill=muted)
        draw.text((x - 35, y - 34), f"{value:.3f}", font=font(16, True), fill=blue)
    draw.line(points, fill=blue, width=5, joint="curve")
    draw.text((85, y0 - 5), "0.065 m/s", font=font(15), fill=muted)
    draw.text((90, y0 + height - 12), "0", font=font(15), fill=muted)

    draw.rounded_rectangle((55, 2670, 1545, 2835), radius=18, fill=pale_green, outline=green, width=3)
    draw.text((85, 2695), "この結果で確認できたこと", font=font(26, True), fill=ink)
    draw.text((90, 2745), "S01から連続して計算できる／5時刻の直接計算結果が揃う／数値検査に合格", font=font(22, True), fill=green)
    draw.text((90, 2790), "未確認：実際の遠賀川との一致／当日の予報精度／ブラウザ補間の誤差", font=font(21, True), fill=red)

    draw.text((55, 2880), "あなたが判断すること", font=font(30, True), fill=ink)
    draw.rounded_rectangle((55, 2935, 1545, 3125), radius=20, fill=pale_blue, outline=blue, width=4)
    draw.rounded_rectangle((85, 2965, 215, 3023), radius=14, fill=blue)
    draw.text((128, 2975), "A", font=font(28, True), fill=white)
    draw.text((245, 2964), "S02を基準資料に採用し、比較検証を作る（推奨）", font=font(29, True), fill=ink)
    draw.text((90, 3045), "直接計算・ブラウザ補間・誤差地図を並べる。追加の物理計算はまだ行わない。", font=font(20), fill=ink)
    draw.text((90, 3085), "S03・残り64区間・main・公開は停止したまま。", font=font(18, True), fill=blue)

    draw.rounded_rectangle((55, 3165, 1545, 3310), radius=20, fill=pale_orange, outline=orange, width=3)
    draw.rounded_rectangle((85, 3195, 215, 3253), radius=14, fill=orange)
    draw.text((128, 3205), "B", font=font(28, True), fill=white)
    draw.text((245, 3195), "S02結果を保存し、比較検証を作らず停止", font=font(29, True), fill=ink)
    draw.text((90, 3260), "追加作業は行わない。実際の川やブラウザ補間との一致は未確認のまま。", font=font(19), fill=ink)

    draw.text((55, 3330), "返信：A＝比較検証を作る　／　B＝ここで停止", font=font(24, True), fill=ink)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=88, optimize=True, progressive=True)
    print(f"{output.relative_to(root)}\t{sha256(output)}\t{output.stat().st_size}")


if __name__ == "__main__":
    main()
