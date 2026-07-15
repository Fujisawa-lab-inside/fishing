#!/usr/bin/env python3
"""Render the Stage 20 browser-compute architecture decision image."""

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


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill, outline, width=2) -> None:
    draw.rounded_rectangle(box, radius=24, fill=fill, outline=outline, width=width)


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], colour) -> None:
    draw.line((start, end), fill=colour, width=8)
    x, y = end
    draw.polygon(((x, y), (x - 18, y - 12), (x - 18, y + 12)), fill=colour)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", default="config/stage20_browser_compute_architecture_candidate_v1.json")
    parser.add_argument("--output", default="docs/visuals/stage20-browser-compute-architecture-v1.jpg")
    args = parser.parse_args()
    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))

    canvas = Image.new("RGB", (1500, 1160), (243, 247, 248))
    draw = ImageDraw.Draw(canvas)
    ink = (23, 49, 61)
    muted = (76, 101, 112)
    green = (37, 115, 92)
    green_soft = (231, 245, 239)
    orange = (166, 88, 42)
    orange_soft = (255, 241, 229)
    border = (194, 208, 214)

    draw.text((55, 35), "次に決めること　36時間をどう計算するか", font=font(40, True), fill=ink)
    draw.text((55, 90), "過去12時間＋未来24時間／地図は1時間ごと／計算はページを開いた端末", font=font(22), fill=muted)

    rounded(draw, (55, 145, 1445, 265), (255, 255, 255), border)
    draw.text((85, 170), "現行の高精度計算をそのまま36時間へ延長", font=font(21), fill=muted)
    draw.text((85, 212), "1条件で約4.4日", font=font(31, True), fill=orange)
    draw.text((370, 219), "現行CPU実測からの単純概算。ブラウザ実測ではなく、時間保証でもない。", font=font(18), fill=muted)

    rounded(draw, (55, 310, 955, 865), green_soft, green, 4)
    draw.text((90, 345), "A　高精度事前計算＋ブラウザ合成（推奨）", font=font(28, True), fill=green)

    rounded(draw, (95, 420, 360, 570), (255, 255, 255), border)
    draw.text((130, 448), "事前計算", font=font(22, True), fill=ink)
    draw.text((125, 493), "代表条件だけ", font=font(19), fill=muted)
    draw.text((125, 528), "高精度に計算", font=font(19), fill=muted)
    arrow(draw, (375, 495), (470, 495), green)
    rounded(draw, (485, 420, 720, 570), (255, 255, 255), border)
    draw.text((530, 448), "GitHub", font=font(22, True), fill=ink)
    draw.text((515, 493), "応答パックを", font=font(19), fill=muted)
    draw.text((515, 528), "静的配信", font=font(19), fill=muted)
    arrow(draw, (735, 495), (810, 495), green)
    rounded(draw, (825, 420, 920, 570), (255, 255, 255), border)
    draw.text((844, 449), "端末", font=font(20, True), fill=ink)
    draw.text((843, 493), "合成", font=font(18), fill=muted)
    draw.text((843, 528), "表示", font=font(18), fill=muted)

    draw.text((95, 625), "・50,339セルの空間表示を維持", font=font(21), fill=ink)
    draw.text((95, 670), "・内部計算は細かく、表示は1時間ごとに37枚", font=font(21), fill=ink)
    draw.text((95, 715), "・補間誤差を物理計算と比較して検証", font=font(21), fill=ink)
    draw.text((95, 760), "・応答パック読込後10秒以内を開発目標", font=font(21), fill=ink)
    draw.text((95, 815), "※ 目標時間は実測前であり保証ではない", font=font(17), fill=muted)

    rounded(draw, (995, 310, 1445, 865), orange_soft, orange, 3)
    draw.text((1030, 345), "B　ブラウザで直接計算", font=font(27, True), fill=orange)
    draw.text((1030, 425), "50,339セルを", font=font(21), fill=ink)
    draw.text((1030, 470), "36時間直接積分", font=font(21), fill=ink)
    draw.text((1030, 550), "高精度計算を", font=font(21), fill=ink)
    draw.text((1030, 595), "そのまま実行できる", font=font(21), fill=ink)
    draw.text((1030, 680), "ただし現行概算", font=font(19), fill=muted)
    draw.text((1030, 725), "約4.4日／1条件", font=font(25, True), fill=orange)
    draw.text((1030, 790), "短時間表示を満たさない", font=font(19), fill=muted)

    rounded(draw, (55, 910, 1445, 1065), (231, 242, 246), (35, 109, 132), 3)
    draw.text((85, 945), "判断することは一つ", font=font(22, True), fill=ink)
    draw.text((85, 990), "A：高精度事前計算＋ブラウザ合成　／　B：ブラウザで36時間を直接計算", font=font(25, True), fill=ink)
    draw.text((85, 1030), "どちらも、この選択だけでは数値実行・公開接続・main反映を行いません。", font=font(17), fill=muted)

    draw.text((55, 1105), "Aでは利用者端末が36時間の条件適用と地図合成を行います。事前計算の実行は後で別途承認を求めます。", font=font(17), fill=muted)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "JPEG", quality=91, optimize=True, progressive=True)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    candidate["visual"] = {"path": str(output), "sha256": digest}
    Path(args.candidate).write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "rendered", "output": str(output), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
