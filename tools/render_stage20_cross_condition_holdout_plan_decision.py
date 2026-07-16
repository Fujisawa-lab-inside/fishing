#!/usr/bin/env python3
"""Render the cross-condition holdout scope decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from render_stage20_hypothetical_routing_preview import font


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color: tuple[int, int, int]) -> None:
    draw.line((*start, *end), fill=color, width=7)
    draw.polygon([(end[0], end[1]), (end[0] - 19, end[1] - 12), (end[0] - 19, end[1] + 12)], fill=color)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="docs/visuals/stage20-cross-condition-holdout-plan-decision.jpg")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    plan = json.loads((root / "config/stage20_cross_condition_holdout_plan_candidate_v1.json").read_text(encoding="utf-8"))

    canvas = Image.new("RGB", (1600, 2590), (243, 247, 248))
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

    draw.text((55, 38), "条件間補間　最初にどこまで検証するか", font=font(42, True), fill=ink)
    draw.text((55, 104), "毎時snapshot保持は採用済み。次は「条件の中間値」を正しく出せるかを確認します。", font=font(22), fill=muted)

    draw.text((55, 168), "推奨する河口堰holdout試験", font=font(30, True), fill=ink)
    boxes = [
        (70, 235, 430, 445, "閉鎖 0%", "新規の直接計算", pale_orange, orange),
        (620, 235, 980, 445, "ブラウザ推定 50%", "0%と100%を50:50", pale_blue, blue),
        (1170, 235, 1530, 445, "全開 100%", "新規の直接計算", pale_orange, orange),
    ]
    for x1, y1, x2, y2, title, subtitle, fill, outline in boxes:
        draw.rounded_rectangle((x1, y1, x2, y2), radius=20, fill=fill, outline=outline, width=4)
        draw.text((x1 + 28, y1 + 50), title, font=font(30, True), fill=ink)
        draw.text((x1 + 28, y1 + 112), subtitle, font=font(20), fill=muted)
    arrow(draw, (435, 340), (605, 340), blue)
    draw.line((1165, 340, 995, 340), fill=blue, width=7)
    draw.polygon([(995, 340), (1014, 328), (1014, 352)], fill=blue)

    draw.rounded_rectangle((360, 510, 1240, 710), radius=20, fill=pale_green, outline=green, width=4)
    draw.text((405, 545), "既存の直接計算 50%", font=font(30, True), fill=ink)
    draw.text((405, 602), "S02の−12〜−8時間・5時刻", font=font(23), fill=ink)
    draw.text((405, 650), "補間材料には使わず、正解として比較", font=font(22, True), fill=green)
    draw.line((800, 445, 800, 495), fill=green, width=6)
    draw.polygon([(800, 510), (788, 488), (812, 488)], fill=green)

    draw.rounded_rectangle((55, 760, 1545, 1010), radius=18, fill=white, outline=grey, width=2)
    draw.text((85, 788), "判定する場所と合格線", font=font(27, True), fill=ink)
    draw.text((90, 842), "5時刻 × 4範囲：河口全域／河口堰／合流部／魚道", font=font(24, True), fill=blue)
    draw.text((90, 895), "速度ベクトルRMSE ≦ 0.010 m/s　　流速MAE ≦ 0.005 m/s", font=font(22), fill=ink)
    draw.text((90, 942), "流向誤差p95 ≦ 5°　　すべての時刻・範囲が合格必須", font=font(22), fill=ink)
    draw.text((1080, 942), "一部合格は不採用", font=font(20, True), fill=red)

    draw.text((55, 1060), "計算量の違い（計画値・まだ実行しない）", font=font(30, True), fill=ink)
    draw.rounded_rectangle((55, 1120, 1545, 1375), radius=18, fill=white, outline=grey, width=2)
    x0, max_w = 300, 1120
    a_w = int(max_w * 8 / 40)
    draw.text((90, 1162), "A  河口堰だけ", font=font(23, True), fill=ink)
    draw.rounded_rectangle((x0, 1160, x0 + a_w, 1215), radius=12, fill=blue)
    draw.text((x0 + a_w + 25, 1167), "8 job／約15.6 runner時間", font=font(22, True), fill=blue)
    draw.text((90, 1260), "B  5入力一括", font=font(23, True), fill=ink)
    draw.rounded_rectangle((x0, 1258, x0 + max_w, 1313), radius=12, fill=orange)
    draw.text((x0 + max_w - 370, 1265), "40 job／約77.9 runner時間", font=font(22, True), fill=white)
    draw.text((90, 1330), "極端条件の速度差、queue・準備・転送・失敗時間は含まないため保証値ではありません。", font=font(18), fill=muted)

    draw.text((55, 1430), "あなたが判断すること", font=font(31, True), fill=ink)
    draw.rounded_rectangle((55, 1495, 1545, 1875), radius=20, fill=pale_blue, outline=blue, width=4)
    draw.rounded_rectangle((85, 1525, 215, 1583), radius=14, fill=blue)
    draw.text((128, 1535), "A", font=font(28, True), fill=white)
    draw.text((245, 1525), "河口堰だけを先に検証する計画（推奨）", font=font(30, True), fill=ink)
    draw.text((90, 1610), "利点：8 jobで最も壊れやすい構造物周辺を先に判定できる。", font=font(22), fill=green)
    draw.text((90, 1660), "利点：不合格なら、他の8基底を計算する前に方式を見直せる。", font=font(22), fill=green)
    draw.text((90, 1710), "欠点：潮位・各河川流量の条件間補間は、まだ未確認のまま。", font=font(22), fill=red)
    draw.text((90, 1780), "次に作るもの：停止状態の8-job contract。実行承認は別画像で判断。", font=font(21, True), fill=blue)
    draw.text((90, 1825), "Aを選んでも、この時点では物理計算を実行しません。", font=font(19), fill=muted)

    draw.rounded_rectangle((55, 1920, 1545, 2290), radius=20, fill=pale_orange, outline=orange, width=3)
    draw.rounded_rectangle((85, 1950, 215, 2008), radius=14, fill=orange)
    draw.text((128, 1960), "B", font=font(28, True), fill=white)
    draw.text((245, 1950), "5入力すべてを一括検証する計画", font=font(30, True), fill=ink)
    draw.text((90, 2035), "利点：潮位・遠賀川・西川・曲川・河口堰を同じ計画で確認できる。", font=font(22), fill=green)
    draw.text((90, 2085), "欠点：約5倍の計算資源。河口堰で失敗しても他の計算費用が発生する。", font=font(22), fill=red)
    draw.text((90, 2155), "次に作るもの：停止状態の40-job contract。実行承認は別画像で判断。", font=font(21, True), fill=orange)
    draw.text((90, 2200), "Bを選んでも、この時点では物理計算を実行しません。", font=font(19), fill=muted)

    draw.rounded_rectangle((55, 2335, 1545, 2510), radius=18, fill=white, outline=grey, width=2)
    draw.text((85, 2365), "返信：A＝河口堰を先に8 job　／　B＝5入力を一括40 job", font=font(26, True), fill=ink)
    draw.text((85, 2420), "どちらも今回はcontract作成だけ。物理run・S03・公開・main反映は承認しません。", font=font(20, True), fill=red)
    draw.text((85, 2462), "計画値：A 約15.6 runner時間　／　B 約77.9 runner時間", font=font(18), fill=muted)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=89, optimize=True, progressive=True)
    print(f"{output.relative_to(root)}\t{sha256(output)}\t{output.stat().st_size}")


if __name__ == "__main__":
    main()
