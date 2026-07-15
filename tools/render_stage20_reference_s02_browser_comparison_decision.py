#!/usr/bin/env python3
"""Render the S02 direct/browser/error comparison decision sheet."""

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
    canvas = Image.new("RGB", size, (230, 237, 240))
    canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def metric_bar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    value: float,
    threshold: float,
    label: str,
    display: str,
    color: tuple[int, int, int],
) -> None:
    ink = (22, 47, 59)
    muted = (65, 88, 100)
    track = (220, 228, 232)
    red = (164, 53, 43)
    draw.text((x, y), label, font=font(19, True), fill=ink)
    draw.text((x + width - 315, y), display, font=font(19, True), fill=color)
    top = y + 38
    draw.rounded_rectangle((x, top, x + width, top + 20), radius=10, fill=track)
    scale = max(value, threshold) * 1.15
    value_width = max(4, int(width * value / scale))
    threshold_x = x + int(width * threshold / scale)
    draw.rounded_rectangle((x, top, x + value_width, top + 20), radius=10, fill=color)
    draw.line((threshold_x, top - 7, threshold_x, top + 28), fill=red, width=4)
    draw.text((max(x, threshold_x - 58), top + 31), "基準", font=font(15), fill=red)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--output",
        default="docs/visuals/stage20-reference-s02-browser-comparison-decision.jpg",
    )
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    evaluation = json.loads(
        (root / "config/stage20_reference_s02_browser_comparison_v1.json").read_text(encoding="utf-8")
    )
    result_root = root / "docs/results/stage20-reference-s02-29434250546"
    direct_path = result_root / "maps/hour-11/pilot-estuary.jpg"
    predicted_path = result_root / "browser-comparison/maps/predicted/pilot-estuary.jpg"
    error_path = result_root / "browser-comparison/maps/error/pilot-estuary.jpg"

    canvas = Image.new("RGB", (1600, 2520), (243, 247, 248))
    draw = ImageDraw.Draw(canvas)
    ink = (22, 47, 59)
    muted = (65, 88, 100)
    blue = (16, 112, 174)
    green = (28, 130, 72)
    orange = (190, 103, 26)
    red = (164, 53, 43)
    white = (255, 255, 255)
    pale_blue = (225, 241, 248)
    pale_green = (225, 244, 232)
    pale_orange = (252, 239, 221)
    grey = (180, 195, 202)

    draw.text((55, 38), "S02 直接計算とブラウザ表示の比較", font=font(42, True), fill=ink)
    draw.text(
        (55, 104),
        "最も誤差が大きかった−11時間を、直接計算・欠落時刻の推定・誤差で並べました。",
        font=font(22),
        fill=muted,
    )

    labels = [
        ("1  直接計算（正解扱い）", "0〜0.23 m/s", direct_path),
        ("2  ブラウザ側の推定", "−12hと−10hの中間", predicted_path),
        ("3  速度ベクトル誤差", "0〜0.04 m/s", error_path),
    ]
    card_w = 490
    for index, (title, subtitle, path) in enumerate(labels):
        x = 55 + index * 510
        y = 165
        draw.rounded_rectangle((x, y, x + card_w, y + 585), radius=17, fill=white, outline=grey, width=2)
        draw.text((x + 18, y + 18), title, font=font(23, True), fill=ink)
        draw.text((x + 18, y + 58), subtitle, font=font(17), fill=muted)
        thumb = fit_image(path, (470, 475))
        canvas.paste(thumb, (x + 10, y + 98))

    draw.rounded_rectangle((55, 790, 1545, 1000), radius=18, fill=pale_orange, outline=orange, width=3)
    draw.text((85, 815), "画像から分かること", font=font(27, True), fill=ink)
    draw.text(
        (90, 866),
        "全体像は似ていますが、誤差地図では上流側と河口堰・分流周辺に局所差が見えます。",
        font=font(24, True),
        fill=orange,
    )
    draw.text(
        (90, 916),
        "したがって「前後2時刻を直線で混ぜれば十分」とは判断できません。",
        font=font(22),
        fill=ink,
    )
    draw.text((90, 958), "※誤差矢印は推定−直接計算。実測値との比較ではありません。", font=font(18), fill=muted)

    worst = evaluation["missingHourLinearFallback"]["worstMetrics"]
    thresholds = evaluation["thresholds"]
    draw.text((55, 1045), "数値判定（−11時間）", font=font(30, True), fill=ink)
    draw.rounded_rectangle((55, 1100, 1545, 1450), radius=18, fill=white, outline=grey, width=2)
    metric_bar(
        draw,
        90,
        1130,
        1350,
        float(worst["velocityVectorRmseMPS"]),
        float(thresholds["maximumLeaveOneOutVelocityVectorRmseMPS"]),
        "速度ベクトルRMSE",
        f"{worst['velocityVectorRmseMPS']:.4f} m/s  ＞  0.0100  不合格",
        red,
    )
    metric_bar(
        draw,
        90,
        1230,
        1350,
        float(worst["speedMaeMPS"]),
        float(thresholds["maximumLeaveOneOutSpeedMaeMPS"]),
        "流速の平均絶対誤差",
        f"{worst['speedMaeMPS']:.5f} m/s  ＞  0.00500  不合格",
        red,
    )
    metric_bar(
        draw,
        90,
        1330,
        1350,
        float(worst["p95DirectionErrorDeg"]),
        float(thresholds["maximumLeaveOneOutP95DirectionErrorDeg"]),
        "流向誤差 p95",
        f"{worst['p95DirectionErrorDeg']:.2f}°  ≦  5.00°  合格",
        green,
    )

    draw.rounded_rectangle((55, 1495, 1545, 1700), radius=18, fill=pale_green, outline=green, width=3)
    draw.text((85, 1520), "今回採用できる結論", font=font(27, True), fill=ink)
    draw.text((90, 1572), "毎時の直接計算snapshotをそのままブラウザへ渡す経路：合格", font=font(24, True), fill=green)
    draw.text((90, 1620), "欠けた1時間を前後の時刻から直線補間する代替経路：不採用", font=font(24, True), fill=red)
    draw.text(
        (90, 1660),
        "直接計算→float32化の速度RMSEは2.33e-9 m/s。条件間の補間精度はまだ未確認です。",
        font=font(19),
        fill=muted,
    )

    draw.text((55, 1750), "あなたが判断すること", font=font(30, True), fill=ink)
    draw.rounded_rectangle((55, 1805, 1545, 2075), radius=20, fill=pale_blue, outline=blue, width=4)
    draw.rounded_rectangle((85, 1835, 215, 1893), radius=14, fill=blue)
    draw.text((128, 1845), "A", font=font(28, True), fill=white)
    draw.text((245, 1835), "この比較結果を採用する（推奨）", font=font(30, True), fill=ink)
    draw.text((90, 1915), "表示する全時刻のsnapshotを事前計算に含め、欠落時刻の直線補間を禁止します。", font=font(21), fill=ink)
    draw.text((90, 1960), "次は、異なる条件間の補間精度を確かめる試験計画だけを作成します。", font=font(21), fill=ink)
    draw.text((90, 2005), "この選択だけでは追加の物理計算・S03・main反映・公開を行いません。", font=font(19, True), fill=blue)

    draw.rounded_rectangle((55, 2115, 1545, 2330), radius=20, fill=pale_orange, outline=orange, width=3)
    draw.rounded_rectangle((85, 2145, 215, 2203), radius=14, fill=orange)
    draw.text((128, 2155), "B", font=font(28, True), fill=white)
    draw.text((245, 2145), "比較結果を採用せず、S02で停止", font=font(30, True), fill=ink)
    draw.text((90, 2225), "ブラウザ用の毎時snapshot方針を確定せず、以後の検証計画も作りません。", font=font(21), fill=ink)
    draw.text((90, 2270), "S02の直接計算結果と証拠はそのまま保存します。", font=font(19), fill=muted)

    draw.text((55, 2385), "返信：A＝比較結果を採用して次の試験計画へ　／　B＝S02で停止", font=font(25, True), fill=ink)
    draw.text((55, 2440), "未確認：実際の遠賀川との一致、当日の予報精度、異なる条件間の補間精度", font=font(19), fill=red)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=89, optimize=True, progressive=True)
    print(f"{output.relative_to(root)}\t{sha256(output)}\t{output.stat().st_size}")


if __name__ == "__main__":
    main()
