#!/usr/bin/env python3
"""Render the kernel-v3 physical result and next planning decision."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from render_stage20_hypothetical_routing_preview import font


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fit_image(path: Path, size: tuple[int, int]) -> Image.Image:
    image = Image.open(path).convert("RGB")
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="docs/visuals/stage20-kernel-v3-physical-result-decision.jpg")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    maps = root / "docs/results/stage20-kernel-v3-physical-pilot-29411976467/maps"

    canvas = Image.new("RGB", (1400, 2200), (243, 247, 248))
    draw = ImageDraw.Draw(canvas)
    ink = (22, 47, 59)
    muted = (65, 88, 100)
    blue = (16, 112, 174)
    green = (28, 130, 72)
    orange = (190, 103, 26)
    red = (155, 51, 42)
    white = (255, 255, 255)
    pale_blue = (225, 241, 248)
    pale_orange = (252, 239, 221)

    draw.text((55, 36), "kernel v3　物理10分の一回確認は合格", font=font(42, True), fill=ink)
    draw.text((55, 102), "次に判断するのは『36時間の分割実行計画を作るか』です。まだ11基底は実行しません。", font=font(22), fill=muted)

    labels = [
        ("pilot-estuary.jpg", "河口全域"),
        ("pilot-barrage.jpg", "河口堰付近"),
        ("pilot-confluence.jpg", "曲川・遠賀川合流"),
        ("pilot-fishway.jpg", "魚道付近"),
    ]
    positions = [(55, 165), (715, 165), (55, 525), (715, 525)]
    for (name, label), (x, y) in zip(labels, positions, strict=True):
        draw.rounded_rectangle((x, y, x + 630, y + 325), radius=14, fill=white, outline=(180, 195, 202), width=2)
        image = fit_image(maps / name, (606, 265))
        canvas.paste(image, (x + 12, y + 48))
        draw.text((x + 16, y + 10), label, font=font(22, True), fill=ink)

    draw.rounded_rectangle((55, 900, 1345, 1255), radius=18, fill=white, outline=(180, 195, 202), width=2)
    draw.text((85, 928), "旧kernel v2との比較", font=font(28, True), fill=ink)
    draw.text((85, 988), "数値差", font=font(21, True), fill=muted)
    draw.text((245, 976), "最大 3.27e−15", font=font(30, True), fill=green)
    draw.text((585, 988), "許容 1e−12以下", font=font(21), fill=ink)
    draw.text((85, 1045), "4地点地図", font=font(21, True), fill=muted)
    draw.text((245, 1036), "すべてbyte単位で同一", font=font(27, True), fill=green)

    draw.text((85, 1110), "実測計算時間", font=font(21, True), fill=muted)
    x0, y0, maxw = 300, 1120, 900
    oldw = maxw
    neww = int(maxw * 304.202253369 / 1492.625987149)
    draw.rounded_rectangle((x0, y0, x0 + oldw, y0 + 38), radius=10, fill=(207, 216, 220))
    draw.rounded_rectangle((x0, y0 + 60, x0 + neww, y0 + 98), radius=10, fill=blue)
    draw.text((x0 + 12, y0 + 5), "v2　24分52.6秒", font=font(19, True), fill=ink)
    draw.text((x0 + neww + 18, y0 + 64), "v3　5分04.2秒　4.91倍", font=font(20, True), fill=green)
    draw.text((85, 1225), "CFL 0.12　質量誤差 2.20e−14　NaN 0　負水深0　checkpoint 10/10", font=font(20), fill=ink)

    draw.rounded_rectangle((55, 1300, 1345, 1515), radius=18, fill=pale_blue, outline=blue, width=3)
    draw.text((85, 1328), "36時間×11基底の更新見積り", font=font(28, True), fill=ink)
    draw.text((85, 1388), "kernel v2計画", font=font(20), fill=muted)
    draw.text((310, 1380), "198区間／約985 runner時間", font=font(26, True), fill=red)
    draw.text((85, 1442), "kernel v3計画", font=font(20), fill=muted)
    draw.text((310, 1434), "44区間／約201 runner時間", font=font(28, True), fill=blue)
    draw.text((875, 1442), "理想経過 約18.25時間＋諸経費", font=font(19), fill=ink)
    draw.text((85, 1482), "queue・setup・転送・再開・失敗区間は未算入。36時間を実行した結果ではありません。", font=font(17), fill=muted)

    draw.text((55, 1565), "あなたが判断すること", font=font(30, True), fill=ink)

    draw.rounded_rectangle((55, 1620, 1345, 1855), radius=20, fill=pale_blue, outline=blue, width=4)
    draw.rounded_rectangle((85, 1650, 215, 1708), radius=14, fill=blue)
    draw.text((128, 1660), "A", font=font(28, True), fill=white)
    draw.text((245, 1650), "kernel v3を採用し、36時間の分割実行計画を作る（推奨）", font=font(28, True), fill=ink)
    draw.text((90, 1732), "得るもの：44区間のcheckpoint、依存関係、失敗時停止、証拠保存の設計", font=font(21), fill=ink)
    draw.text((90, 1780), "この選択では11基底を実行しない。実行前に別の画像で再度判断する。", font=font(21, True), fill=blue)
    draw.text((90, 1822), "理由：結果同一性と実測4.91倍を確認済みで、計画作成へ進めるため。", font=font(18), fill=muted)

    draw.rounded_rectangle((55, 1900, 1345, 2100), radius=20, fill=pale_orange, outline=orange, width=3)
    draw.rounded_rectangle((85, 1930, 215, 1988), radius=14, fill=orange)
    draw.text((128, 1940), "B", font=font(28, True), fill=white)
    draw.text((245, 1930), "採用せず、追加のコード限定高速化を検討する", font=font(28, True), fill=ink)
    draw.text((90, 2012), "物理runは増えないが、36時間計画の作成を保留する。", font=font(21), fill=ink)
    draw.text((90, 2055), "追加高速化の効果は未確定で、開発期間が延びる。", font=font(19), fill=muted)

    draw.text((55, 2145), "返信：A＝分割計画を作る　／　B＝追加高速化を検討", font=font(24, True), fill=ink)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=86, optimize=True, progressive=True)
    print(f"{output.relative_to(root)}\t{sha256(output)}\t{output.stat().st_size}")


if __name__ == "__main__":
    main()
