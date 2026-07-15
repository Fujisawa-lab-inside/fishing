#!/usr/bin/env python3
"""Render the Stage 20 warmup-canary execution decision."""

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
    parser.add_argument("--output", default="docs/visuals/stage20-36h-canary-execution-decision.jpg")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()

    canvas = Image.new("RGB", (1400, 1980), (243, 247, 248))
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
    grey = (207, 216, 220)

    draw.text((55, 38), "次の判断　最初の助走8時間だけを実行するか", font=font(40, True), fill=ink)
    draw.text((55, 102), "全66区間の承認ではありません。残り65区間は、この結果を見て別に判断します。", font=font(22), fill=muted)

    draw.rounded_rectangle((55, 155, 1345, 430), radius=18, fill=white, outline=(180, 195, 202), width=2)
    draw.text((85, 182), "詳細化で変わった点", font=font(28, True), fill=ink)
    draw.text((85, 238), "旧見積り", font=font(20), fill=muted)
    draw.text((260, 230), "36時間・助走なし　44区間／約201 runner時間", font=font(25, True), fill=red)
    draw.text((85, 294), "修正計画", font=font(20), fill=muted)
    draw.text((260, 286), "12時間助走＋表示36時間　66区間／約268 runner時間", font=font(26, True), fill=blue)
    draw.text((85, 350), "理由", font=font(20, True), fill=muted)
    draw.text((260, 344), "静水から始めた状態を『過去12時間』として表示しないため", font=font(23, True), fill=green)
    draw.text((85, 394), "精度を優先した修正。66区間はまだ一つも実行していません。", font=font(18), fill=muted)

    draw.rounded_rectangle((55, 475, 1345, 790), radius=18, fill=white, outline=(180, 195, 202), width=2)
    draw.text((85, 500), "時間の分割", font=font(27, True), fill=ink)
    x0, y0, width = 120, 590, 1160
    block = width / 6
    labels = ["S01\n-24→-16", "S02\n-16→-8", "S03\n-8→0", "S04\n0→+8", "S05\n+8→+16", "S06\n+16→+24"]
    for index, label in enumerate(labels):
        left = int(x0 + index * block)
        right = int(x0 + (index + 1) * block - 5)
        fill = pale_orange if index == 0 else pale_blue
        outline = orange if index == 0 else blue
        draw.rounded_rectangle((left, y0, right, y0 + 95), radius=12, fill=fill, outline=outline, width=3)
        first, second = label.split("\n")
        draw.text((left + 48, y0 + 12), first, font=font(21, True), fill=ink)
        draw.text((left + 28, y0 + 51), second, font=font(18), fill=ink)
    requested_x = int(x0 + width * 12 / 48)
    draw.line((requested_x, y0 - 25, requested_x, y0 + 135), fill=green, width=5)
    draw.polygon([(requested_x, y0 - 25), (requested_x - 10, y0 - 8), (requested_x + 10, y0 - 8)], fill=green)
    draw.text((requested_x + 12, y0 - 25), "表示開始 -12h", font=font(18, True), fill=green)
    draw.text((120, 715), "助走12h", font=font(20, True), fill=orange)
    draw.line((220, 730, requested_x - 15, 730), fill=orange, width=4)
    draw.text((requested_x + 15, 715), "表示対象37枚（-12h〜+24h、1時間間隔）", font=font(20, True), fill=blue)
    draw.text((85, 758), "各segmentは8物理時間。直前checkpointのSHA-256一致がないと開始できません。", font=font(18), fill=muted)

    draw.rounded_rectangle((55, 835, 1345, 1125), radius=18, fill=pale_blue, outline=blue, width=3)
    draw.text((85, 862), "今回Aで実行する範囲：reference-s01だけ", font=font(29, True), fill=ink)
    draw.rounded_rectangle((85, 925, 300, 1015), radius=14, fill=orange)
    draw.text((118, 945), "-24 → -16h", font=font(24, True), fill=white)
    draw.text((340, 920), "物理時間", font=font(18), fill=muted)
    draw.text((340, 955), "8時間", font=font(31, True), fill=ink)
    draw.text((570, 920), "runner開始後の予測", font=font(18), fill=muted)
    draw.text((570, 955), "約4時間03分", font=font(31, True), fill=blue)
    draw.text((930, 920), "強制停止", font=font(18), fill=muted)
    draw.text((930, 955), "5時間", font=font(31, True), fill=red)
    draw.text((85, 1043), "出力：restart checkpoint・完全な数値証拠・-16h時点の診断地図1枚", font=font(21, True), fill=ink)
    draw.text((85, 1083), "queue待ちとsetupは予測外／一回限り／自動retryなし／成功しても残り65区間は停止", font=font(18), fill=muted)

    draw.rounded_rectangle((55, 1170, 1345, 1385), radius=18, fill=white, outline=(180, 195, 202), width=2)
    draw.text((85, 1195), "主なリスク", font=font(27, True), fill=ink)
    draw.text((90, 1250), "・計算速度が10分pilotから変化し、5時間で未完了停止する可能性", font=font(20), fill=red)
    draw.text((90, 1295), "・8時間を進めて初めて現れる数値不安定性や潮汐応答がある可能性", font=font(20), fill=red)
    draw.text((90, 1340), "・この助走地図は釣況予測ではなく、計算継続可否の診断資料", font=font(20), fill=ink)

    draw.text((55, 1435), "あなたが判断すること", font=font(30, True), fill=ink)
    draw.rounded_rectangle((55, 1490, 1345, 1705), radius=20, fill=pale_blue, outline=blue, width=4)
    draw.rounded_rectangle((85, 1520, 215, 1578), radius=14, fill=blue)
    draw.text((128, 1530), "A", font=font(28, True), fill=white)
    draw.text((245, 1520), "reference-s01を一回だけ実行する（推奨）", font=font(30, True), fill=ink)
    draw.text((90, 1600), "8物理時間／予測約4時間03分／最大5時間／自動retryなし", font=font(22), fill=ink)
    draw.text((90, 1650), "残り65区間・公開・main反映・物理Validationは承認しない", font=font(20, True), fill=blue)

    draw.rounded_rectangle((55, 1750, 1345, 1905), radius=20, fill=pale_orange, outline=orange, width=3)
    draw.rounded_rectangle((85, 1780, 215, 1838), radius=14, fill=orange)
    draw.text((128, 1790), "B", font=font(28, True), fill=white)
    draw.text((245, 1780), "実行せず、66区間の計画だけで停止する", font=font(30, True), fill=ink)
    draw.text((90, 1855), "計算資源と実行リスクは発生しない。8時間実測は未確認のまま。", font=font(21), fill=ink)

    draw.text((55, 1935), "返信：A＝最初の1区間だけ実行　／　B＝実行しない", font=font(24, True), fill=ink)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=87, optimize=True, progressive=True)
    print(f"{output.relative_to(root)}\t{sha256(output)}\t{output.stat().st_size}")


if __name__ == "__main__":
    main()
