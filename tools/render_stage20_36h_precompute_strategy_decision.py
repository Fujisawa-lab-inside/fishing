#!/usr/bin/env python3
"""Render the Stage 20 36-hour precompute route decision."""

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
    parser.add_argument("--output", default="docs/visuals/stage20-36h-precompute-strategy-decision.jpg")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()

    canvas = Image.new("RGB", (1300, 1680), (243, 247, 248))
    draw = ImageDraw.Draw(canvas)
    ink = (22, 47, 59)
    muted = (65, 88, 100)
    blue = (16, 112, 174)
    green = (28, 130, 72)
    orange = (190, 103, 26)
    red = (155, 51, 42)
    pale_blue = (225, 241, 248)
    pale_orange = (252, 239, 221)
    white = (255, 255, 255)

    draw.text((55, 40), "36時間応答基底　次に決めるのは「計算経路」", font=font(39, True), fill=ink)
    draw.text((55, 105), "流向表示は採用済み。ここでは物理の正しさや公開可否を判断しません。", font=font(22), fill=muted)

    draw.rounded_rectangle((55, 165, 1245, 425), radius=18, fill=white, outline=(180, 195, 202), width=2)
    draw.text((85, 192), "実測からの現行kernel v2延長", font=font(27, True), fill=ink)
    draw.text((85, 248), "10分 = 24分52.6秒", font=font(25), fill=ink)
    draw.line((355, 267, 505, 267), fill=blue, width=5)
    draw.polygon([(505, 267), (485, 255), (485, 279)], fill=blue)
    draw.text((545, 240), "36時間 × 11基底", font=font(25), fill=ink)
    draw.text((85, 318), "約985 runner時間　／　5時間区切りで198 job区間", font=font(31, True), fill=red)
    draw.text((85, 370), "11本を並列化しても理想約3.7日＋queue・転送・再開時間", font=font(21), fill=muted)

    draw.text((55, 475), "どちらの経路を採用するか", font=font(30, True), fill=ink)

    draw.rounded_rectangle((55, 535, 1245, 905), radius=20, fill=pale_blue, outline=blue, width=4)
    draw.rounded_rectangle((85, 565, 215, 620), radius=14, fill=blue)
    draw.text((128, 575), "A", font=font(27, True), fill=white)
    draw.text((245, 565), "コンパイル済みkernel v3を先に開発（推奨）", font=font(29, True), fill=ink)
    draw.text((90, 648), "変えない", font=font(20, True), fill=green)
    draw.text((225, 648), "mesh・流束・境界・摩擦・CFL・float64", font=font(21), fill=ink)
    draw.text((90, 700), "まず行う", font=font(20, True), fill=green)
    draw.text((225, 700), "物理時間を進めない300-step同値性＋速度試験", font=font(21), fill=ink)
    draw.text((90, 752), "合格線", font=font(20, True), fill=green)
    draw.text((225, 752), "相対差 1e−12以下、NaN 0、負水深0、速度目標 5倍以上", font=font(21), fill=ink)
    draw.text((90, 816), "合格後に、1回限りの物理10分benchmarkを別画像で判断", font=font(23, True), fill=blue)
    draw.text((90, 858), "このA選択だけでは物理計算を実行しない", font=font(19), fill=muted)

    draw.rounded_rectangle((55, 950, 1245, 1265), radius=20, fill=pale_orange, outline=orange, width=3)
    draw.rounded_rectangle((85, 980, 215, 1035), radius=14, fill=orange)
    draw.text((128, 990), "B", font=font(27, True), fill=white)
    draw.text((245, 980), "現行kernel v2のまま198区間を計画", font=font(29, True), fill=ink)
    draw.text((90, 1060), "実装変更は少ないが、約985 runner時間が必要", font=font(23), fill=ink)
    draw.text((90, 1112), "大量・長時間job、失敗時の再承認、運用負担が大きい", font=font(23), fill=ink)
    draw.text((90, 1175), "このB選択だけでもcampaignは開始しない", font=font(19), fill=muted)

    draw.rounded_rectangle((55, 1320, 1245, 1615), radius=18, fill=white, outline=green, width=4)
    draw.text((85, 1352), "あなたが判断すること", font=font(27, True), fill=ink)
    draw.text((85, 1408), "A　コード高速化を先に行う", font=font(29, True), fill=blue)
    draw.text((85, 1464), "B　現行のまま198区間計画を採用する", font=font(29, True), fill=orange)
    draw.text((85, 1532), "推奨はA。返信は「A」または「B」だけで進められます。", font=font(22, True), fill=ink)
    draw.text((85, 1572), "どちらも追加物理run・公開・main反映を承認しません。", font=font(18), fill=muted)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=84, optimize=True, progressive=True)
    print(f"{output.relative_to(root)}\t{sha256(output)}\t{output.stat().st_size}")


if __name__ == "__main__":
    main()
