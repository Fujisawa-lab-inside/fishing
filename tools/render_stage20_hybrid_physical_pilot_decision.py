#!/usr/bin/env python3
"""Render the one-time hybrid physical-pilot execution decision."""

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


def box(draw, coordinates, fill, outline, width=2):
    draw.rounded_rectangle(coordinates, radius=22, fill=fill, outline=outline, width=width)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", default="config/stage20_hybrid_physical_pilot_candidate_v1.json")
    parser.add_argument("--output", default="docs/visuals/stage20-hybrid-physical-pilot-decision-v1.jpg")
    args = parser.parse_args()
    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    canvas = Image.new("RGB", (1500, 1080), (243, 247, 248))
    draw = ImageDraw.Draw(canvas)
    ink = (23, 49, 61)
    muted = (75, 99, 110)
    blue = (31, 105, 133)
    blue_soft = (230, 242, 246)
    green = (38, 116, 91)
    green_soft = (231, 245, 239)
    orange = (163, 86, 41)
    orange_soft = (255, 241, 229)
    border = (193, 207, 213)

    draw.text((55, 35), "次の判断　短い物理パイロットを実行するか", font=font(39, True), fill=ink)
    draw.text((55, 88), "A案のブラウザ合成は実装済み。次は物理計算との接続を1条件だけ確認します。", font=font(21), fill=muted)

    box(draw, (55, 145, 1445, 290), (255, 255, 255), border)
    draw.text((85, 175), "計算資源", font=font(19), fill=muted)
    draw.text((85, 217), "GitHub提供 Linux x86 runner", font=font(29, True), fill=blue)
    draw.text((660, 175), "範囲", font=font(19), fill=muted)
    draw.text((660, 217), "1条件 × 物理時間10分 × 一回限り", font=font(27, True), fill=ink)
    draw.text((85, 263), "実行時間概算：約29分／強制停止上限：90分（概算は保証ではありません）", font=font(18), fill=muted)

    box(draw, (55, 335, 935, 780), blue_soft, blue, 3)
    draw.text((90, 370), "実行条件と得られるもの", font=font(27, True), fill=blue)
    draw.text((90, 430), "条件", font=font(20, True), fill=ink)
    draw.text((180, 430), "雨後3日相当・河口堰全開・大潮相当・下げ三分", font=font(20), fill=ink)
    draw.text((90, 485), "保存", font=font(20, True), fill=ink)
    draw.text((180, 485), "60秒ごとの再開用チェックポイント", font=font(20), fill=ink)
    draw.text((90, 540), "数値", font=font(20, True), fill=ink)
    draw.text((180, 540), "質量収支・CFL・水深正値・非有限値の検査", font=font(20), fill=ink)
    draw.text((90, 595), "画像", font=font(20, True), fill=ink)
    draw.text((180, 595), "河口全域／河口堰／合流点／魚道の4画面", font=font(20), fill=ink)
    draw.text((90, 650), "用途", font=font(20, True), fill=ink)
    draw.text((180, 650), "物理計算→応答パック→ブラウザ表示の接続確認", font=font(20), fill=ink)
    draw.text((90, 720), "この1回だけでは36時間の応答基底や物理的正しさは確認できません。", font=font(18), fill=muted)

    box(draw, (975, 335, 1445, 780), orange_soft, orange, 3)
    draw.text((1010, 370), "発生し得ること", font=font(26, True), fill=orange)
    draw.text((1010, 440), "・実行時間が概算を超える", font=font(19), fill=ink)
    draw.text((1010, 495), "・数値検査で途中停止する", font=font(19), fill=ink)
    draw.text((1010, 550), "・推論入力が実際と異なる", font=font(19), fill=ink)
    draw.text((1010, 605), "・GitHub側の一時障害", font=font(19), fill=ink)
    draw.text((1010, 690), "有料クラウドや", font=font(19, True), fill=orange)
    draw.text((1010, 730), "self-hosted機は使いません", font=font(19, True), fill=orange)

    box(draw, (55, 835, 1445, 1000), green_soft, green, 4)
    draw.text((85, 870), "判断することは一つ", font=font(21, True), fill=ink)
    draw.text((85, 920), "A：この1条件10分を一回だけ実行　／　B：まだ実行せずコード作業だけ続ける", font=font(25, True), fill=ink)
    draw.text((85, 965), "Aでも、11条件の事前計算・有料資源・公開接続・main反映は承認されません。", font=font(17), fill=muted)
    draw.text((55, 1030), "実行workflowと一回限りgateを固定した後、実行直前に承認文とSHA-256を照合します。", font=font(17), fill=muted)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "JPEG", quality=91, optimize=True, progressive=True)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    candidate["visual"] = {"path": str(output), "sha256": digest}
    Path(args.candidate).write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "rendered", "output": str(output), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
