#!/usr/bin/env python3
"""Render the Stage 20 kernel v3 code-only result and physical-pilot decision."""

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
    parser.add_argument("--output", default="docs/visuals/stage20-kernel-v3-result-decision.jpg")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()

    canvas = Image.new("RGB", (1300, 1660), (243, 247, 248))
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

    draw.text((55, 38), "kernel v3　コード限定Linux x86試験は合格", font=font(39, True), fill=ink)
    draw.text((55, 98), "物理runはまだ実行していません。次に判断するのは1回の確認runです。", font=font(22), fill=muted)

    draw.rounded_rectangle((55, 160, 1245, 440), radius=18, fill=white, outline=(180, 195, 202), width=2)
    draw.text((85, 188), "確定したコード試験結果", font=font(27, True), fill=ink)
    draw.text((85, 250), "速度", font=font(21, True), fill=muted)
    draw.text((250, 238), "7.92倍", font=font(38, True), fill=green)
    draw.text((500, 250), "目標5倍以上　合格", font=font(24, True), fill=green)
    draw.text((85, 318), "数値差", font=font(21, True), fill=muted)
    draw.text((250, 310), "6.27e-16", font=font(30, True), fill=ink)
    draw.text((500, 318), "許容1e-12以下　合格", font=font(23, True), fill=green)
    draw.text((85, 378), "NaN 0　負水深0　模擬時間差0　300 step×各5回", font=font(21), fill=ink)

    draw.rounded_rectangle((55, 485, 1245, 720), radius=18, fill=pale_blue, outline=blue, width=3)
    draw.text((85, 515), "実際の物理10分に単純換算した予測", font=font(27, True), fill=ink)
    draw.text((85, 575), "kernel v2実測", font=font(21), fill=muted)
    draw.text((300, 568), "24分52.6秒", font=font(27, True), fill=ink)
    draw.line((520, 593, 690, 593), fill=blue, width=5)
    draw.polygon([(690, 593), (670, 581), (670, 605)], fill=blue)
    draw.text((735, 575), "kernel v3予測", font=font(21), fill=muted)
    draw.text((960, 568), "約3分08秒", font=font(27, True), fill=blue)
    draw.text((85, 650), "runner開始後はsetup込み約5分を想定／上限20分／queue待ちは別", font=font(22, True), fill=ink)
    draw.text((85, 688), "これは合成試験からの予測であり、実測値・保証値ではありません。", font=font(18), fill=red)

    draw.text((55, 770), "あなたが判断すること：同じ1条件をkernel v3で一回確認するか", font=font(29, True), fill=ink)

    draw.rounded_rectangle((55, 830, 1245, 1115), radius=20, fill=pale_blue, outline=blue, width=4)
    draw.rounded_rectangle((85, 860, 215, 915), radius=14, fill=blue)
    draw.text((128, 870), "A", font=font(27, True), fill=white)
    draw.text((245, 860), "物理10分を一回だけ実行する（推奨）", font=font(29, True), fill=ink)
    draw.text((90, 940), "範囲　mesh v2＋kernel v3／同じ推論入力1条件／600物理秒", font=font(21), fill=ink)
    draw.text((90, 990), "制限　承認後24時間以内／1回／最大20分／自動retryなし", font=font(21), fill=ink)
    draw.text((90, 1040), "得るもの　実際の速度・数値安定性・4地点地図・36時間見積り", font=font(21), fill=ink)
    draw.text((90, 1080), "この1回は36時間campaignを承認しません。", font=font(18), fill=muted)

    draw.rounded_rectangle((55, 1160, 1245, 1375), radius=20, fill=pale_orange, outline=orange, width=3)
    draw.rounded_rectangle((85, 1190, 215, 1245), radius=14, fill=orange)
    draw.text((128, 1200), "B", font=font(27, True), fill=white)
    draw.text((245, 1190), "物理runを行わず、コード試験合格で止める", font=font(29, True), fill=ink)
    draw.text((90, 1270), "計算資源と実行リスクは発生しない", font=font(21), fill=ink)
    draw.text((90, 1320), "ただし物理10分・36時間の実時間見積りは未確認のまま", font=font(21), fill=ink)

    draw.rounded_rectangle((55, 1420, 1245, 1600), radius=18, fill=white, outline=green, width=4)
    draw.text((85, 1452), "返信", font=font(25, True), fill=ink)
    draw.text((205, 1452), "A：一回だけ実行　／　B：実行しない", font=font(27, True), fill=ink)
    draw.text((85, 1510), "主なリスク：予測速度未達、20分で停止、推論入力が実際と異なる可能性", font=font(19), fill=red)
    draw.text((85, 1552), "公開・main反映・11基底campaign・物理Validation主張は含みません。", font=font(18), fill=muted)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=84, optimize=True, progressive=True)
    print(f"{output.relative_to(root)}\t{sha256(output)}\t{output.stat().st_size}")


if __name__ == "__main__":
    main()
