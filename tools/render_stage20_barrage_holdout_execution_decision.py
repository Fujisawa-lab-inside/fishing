#!/usr/bin/env python3
"""Render the one-time barrage holdout execution decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from render_stage20_hypothetical_routing_preview import font


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="docs/visuals/stage20-barrage-holdout-execution-decision.jpg")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    contract = json.loads((root / "config/stage20_barrage_holdout_contract_v1.json").read_text(encoding="utf-8"))

    canvas = Image.new("RGB", (1600, 2640), (243, 247, 248))
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

    draw.text((55, 38), "河口堰条件間補間　8 jobを実行するか", font=font(42, True), fill=ink)
    draw.text((55, 104), "0%・100%を計算し、既存50%を正解として補間精度を判定する一回限りの範囲です。", font=font(22), fill=muted)

    draw.text((55, 175), "実行する2系列（各4 jobは順番、2系列は並列）", font=font(29, True), fill=ink)
    hours = ["−24→−20", "−20→−16", "−16→−12", "−12→−8"]
    for row, (label, color, fill) in enumerate((("河口堰本体 0%", orange, pale_orange), ("河口堰本体 100%", blue, pale_blue))):
        y = 250 + row * 210
        draw.text((60, y + 55), label, font=font(24, True), fill=ink)
        for index, hour in enumerate(hours):
            x = 330 + index * 295
            draw.rounded_rectangle((x, y, x + 245, y + 145), radius=16, fill=fill, outline=color, width=3)
            draw.text((x + 26, y + 25), f"job {index + 1}", font=font(20, True), fill=ink)
            draw.text((x + 26, y + 72), hour, font=font(19), fill=ink)
            if index < 3:
                draw.line((x + 248, y + 73, x + 285, y + 73), fill=grey, width=5)
                draw.polygon([(x + 285, y + 73), (x + 270, y + 63), (x + 270, y + 83)], fill=grey)
    draw.text((330, 650), "各段階で両方が成功した場合だけ次へ進む。一方が失敗すると残りを停止。", font=font(21, True), fill=red)

    draw.rounded_rectangle((55, 720, 1545, 965), radius=18, fill=white, outline=grey, width=2)
    draw.text((85, 748), "時間・計算資源", font=font(27, True), fill=ink)
    metrics = [("実時間", "約8〜10時間"), ("合計計算資源", "約15.6 runner時間"), ("job上限", "各5時間")]
    for index, (label, value) in enumerate(metrics):
        x = 90 + index * 485
        draw.text((x, 810), label, font=font(18), fill=muted)
        draw.text((x, 850), value, font=font(28, True), fill=blue if index < 2 else red)
    draw.text((90, 920), "計画値であり、極端条件の計算速度・queue・導入・転送時間により延びる可能性があります。", font=font(18), fill=muted)

    draw.rounded_rectangle((55, 1015, 1545, 1295), radius=18, fill=pale_green, outline=green, width=3)
    draw.text((85, 1042), "成功したら得られるもの", font=font(27, True), fill=ink)
    draw.text((90, 1095), "0%・100%それぞれ5時刻、合計10個の直接solver snapshot", font=font(23, True), fill=green)
    draw.text((90, 1145), "既存50%と比べる：直接計算／50:50補間／誤差地図（4範囲）", font=font(23, True), fill=green)
    draw.text((90, 1195), "合格線：速度RMSE 0.010 m/s、流速MAE 0.005 m/s、流向p95 5°", font=font(21), fill=ink)
    draw.text((90, 1245), "0%は河口堰本体を閉鎖。魚道は水頭差関係を維持します。", font=font(19, True), fill=orange)

    draw.rounded_rectangle((55, 1345, 1545, 1575), radius=18, fill=pale_orange, outline=orange, width=3)
    draw.text((85, 1372), "主なリスク", font=font(27, True), fill=ink)
    draw.text((90, 1425), "• 1 jobでも5時間超過・数値異常なら残りを停止。自動retryなし。", font=font(22), fill=red)
    draw.text((90, 1472), "• 途中までの計算資源は戻らない。完了時刻はGitHub側の混雑で変わる。", font=font(22), fill=red)
    draw.text((90, 1519), "• 公開データと推論条件の検証であり、実測一致や当日予報の証明ではない。", font=font(21), fill=ink)

    draw.text((55, 1630), "あなたが判断すること", font=font(31, True), fill=ink)
    draw.rounded_rectangle((55, 1695, 1545, 2065), radius=20, fill=pale_blue, outline=blue, width=4)
    draw.rounded_rectangle((85, 1725, 215, 1783), radius=14, fill=blue)
    draw.text((128, 1735), "A", font=font(28, True), fill=white)
    draw.text((245, 1725), "8 jobを一回限り実行する", font=font(30, True), fill=ink)
    draw.text((90, 1810), "承認後24時間以内に、河口堰0%・100%の2系列だけを実行します。", font=font(22), fill=ink)
    draw.text((90, 1860), "成功後は追加計算なしで50% holdout比較と判断画像を作ります。", font=font(22), fill=ink)
    draw.text((90, 1925), "含まない：潮位・河川流量の他8基底、reference S03、retry、公開、main反映", font=font(20, True), fill=blue)
    draw.text((90, 1980), "返信Aだけではなく、下記の固定文面を承認として記録します。", font=font(18), fill=muted)

    draw.rounded_rectangle((55, 2110, 1545, 2325), radius=20, fill=pale_orange, outline=orange, width=3)
    draw.rounded_rectangle((85, 2140, 215, 2198), radius=14, fill=orange)
    draw.text((128, 2150), "B", font=font(28, True), fill=white)
    draw.text((245, 2140), "実行せず、停止状態を維持", font=font(30, True), fill=ink)
    draw.text((90, 2220), "contract・runner・workflowは保存しますが、authorizationとgateを作りません。", font=font(21), fill=ink)
    draw.text((90, 2270), "数値計算は0 stepのままです。", font=font(19), fill=muted)

    draw.rounded_rectangle((55, 2370, 1545, 2570), radius=18, fill=white, outline=grey, width=2)
    draw.text((85, 2395), "Aの承認文面", font=font(24, True), fill=ink)
    text = "承認済み河口堰holdout contract v1上で、0%・100%の8 jobを、承認後24時間以内に一回限り実行してよい。"
    draw.text((85, 2450), text, font=font(21, True), fill=blue)
    draw.text((85, 2510), "Bの場合：実行しない", font=font(19, True), fill=orange)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=89, optimize=True, progressive=True)
    print(f"{output.relative_to(root)}\t{sha256(output)}\t{output.stat().st_size}")


if __name__ == "__main__":
    main()
