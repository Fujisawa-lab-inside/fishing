#!/usr/bin/env python3
"""Render the bounded one-time barrage holdout recovery decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from render_stage20_hypothetical_routing_preview import font


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def box(draw: ImageDraw.ImageDraw, bounds, fill, outline, width: int = 2, radius: int = 18) -> None:
    draw.rounded_rectangle(bounds, radius=radius, fill=fill, outline=outline, width=width)


def arrow(draw: ImageDraw.ImageDraw, start_x: int, end_x: int, y: int, color) -> None:
    draw.line((start_x, y, end_x - 15, y), fill=color, width=5)
    draw.polygon(((end_x, y), (end_x - 17, y - 11), (end_x - 17, y + 11)), fill=color)


def timeline_job(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, title: str, hours: str, state: str, fill, outline, ink) -> None:
    box(draw, (x, y, x + width, y + 130), fill, outline, 3, 15)
    draw.text((x + 18, y + 17), title, font=font(18, True), fill=ink)
    draw.text((x + 18, y + 53), hours, font=font(18), fill=ink)
    draw.text((x + 18, y + 91), state, font=font(16, True), fill=outline)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--contract", default="config/stage20_barrage_holdout_recovery_contract_v1.json")
    parser.add_argument("--output", default="docs/visuals/stage20-barrage-holdout-recovery-decision.jpg")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    contract = json.loads((root / args.contract).read_text(encoding="utf-8"))

    canvas = Image.new("RGB", (1600, 2920), (243, 247, 248))
    draw = ImageDraw.Draw(canvas)
    ink = (22, 47, 59)
    muted = (67, 89, 101)
    blue = (17, 111, 171)
    green = (29, 128, 72)
    orange = (194, 105, 25)
    red = (166, 52, 43)
    white = (255, 255, 255)
    pale_blue = (225, 241, 248)
    pale_green = (226, 244, 232)
    pale_orange = (252, 239, 221)
    pale_red = (250, 229, 226)
    pale_grey = (234, 239, 241)
    grey = (180, 195, 202)

    draw.text((55, 38), "残りの河口堰検証を、一回だけ実行するか", font=font(41, True), fill=ink)
    draw.text((55, 103), "完了済みは再利用。閉鎖側を2時間ずつに分け、開放側の残り1区間も計算します。", font=font(22), fill=muted)

    metrics = (
        ("保存済み", "5区間", "再計算しない", green),
        ("今回の残り", "5区間", "閉鎖4＋開放1", blue),
        ("追加料金", "0円想定※", "現行料金・標準計算機", green),
        ("完了目安", "12〜16時間", "待ち時間で変動", orange),
    )
    for index, (label, value, note, color) in enumerate(metrics):
        x = 55 + index * 380
        box(draw, (x, 165, x + 350, 355), white, grey)
        draw.text((x + 25, 188), label, font=font(18), fill=muted)
        draw.text((x + 25, 230), value, font=font(31, True), fill=color)
        draw.text((x + 25, 300), note, font=font(17), fill=ink)

    draw.text((55, 405), "緑＝保存済み　青＝今回だけ計算　赤い注記＝前回の途中結果は再利用しない", font=font(20, True), fill=ink)

    draw.text((55, 465), "閉鎖0%", font=font(24, True), fill=orange)
    timeline_job(draw, 200, 450, 205, "旧S01", "−24→−20", "保存済み", pale_green, green, ink)
    arrow(draw, 410, 445, 515, grey)
    timeline_job(draw, 450, 450, 205, "旧S02", "−20→−16", "保存済み", pale_green, green, ink)
    arrow(draw, 660, 695, 515, grey)
    timeline_job(draw, 700, 450, 190, "今回1", "−16→−14", "2時間", pale_blue, blue, ink)
    arrow(draw, 895, 925, 515, grey)
    timeline_job(draw, 930, 450, 190, "今回2", "−14→−12", "2時間", pale_blue, blue, ink)
    arrow(draw, 1125, 1155, 515, grey)
    timeline_job(draw, 1160, 450, 190, "今回3", "−12→−10", "2時間", pale_blue, blue, ink)
    arrow(draw, 1355, 1385, 515, grey)
    timeline_job(draw, 1390, 450, 155, "今回4", "−10→−8", "2時間", pale_blue, blue, ink)
    draw.rounded_rectangle((675, 596, 1245, 641), radius=12, fill=pale_red, outline=red, width=2)
    draw.text((695, 606), "前回の75%は未封印のため、閉鎖−16時間から正式にやり直す", font=font(16, True), fill=red)

    draw.text((55, 700), "開放100%", font=font(24, True), fill=blue)
    timeline_job(draw, 200, 685, 205, "旧S01", "−24→−20", "保存済み", pale_green, green, ink)
    arrow(draw, 410, 445, 750, grey)
    timeline_job(draw, 450, 685, 205, "旧S02", "−20→−16", "保存済み", pale_green, green, ink)
    arrow(draw, 660, 695, 750, grey)
    timeline_job(draw, 700, 685, 205, "旧S03", "−16→−12", "保存済み", pale_green, green, ink)
    arrow(draw, 910, 945, 750, grey)
    timeline_job(draw, 950, 685, 350, "今回5", "−12→−8", "4時間", pale_blue, blue, ink)
    draw.text((950, 830), "青い5区間だけを実行", font=font(24, True), fill=blue)

    box(draw, (55, 895, 1545, 1155), pale_green, green, 3)
    draw.text((85, 920), "追加料金を発生させない条件", font=font(28, True), fill=ink)
    draw.text((90, 975), "✓ 公開GitHubリポジトリ　　✓ 標準Linux計算機（ubuntu-latest）　　✓ 有料の大型runnerを使わない", font=font(21, True), fill=green)
    draw.text((90, 1025), "✓ 有料クラウド・自前サーバーを使わない　　✓ 一回限り", font=font(21, True), fill=green)
    draw.text((90, 1070), "GitHub上の一時成果物は30日。確認後、必要な証拠と結果記録は作業ブランチへ保存します。", font=font(18), fill=ink)
    draw.text((90, 1110), "※ 現在のGitHub料金体系を前提とした0円想定です。規約変更や有料計算機への変更は含みません。", font=font(19, True), fill=orange)

    box(draw, (55, 1205, 1545, 1495), white, grey)
    draw.text((85, 1230), "時間は3種類あります", font=font(27, True), fill=ink)
    time_metrics = (
        ("川の時間", "12時間", "計算内で進める合計"),
        ("計算機の使用量", "約14〜17時間", "5区間の使用時間合計"),
        ("結果まで", "約12〜16時間", "並列・準備込みの目安"),
    )
    for index, (label, value, note) in enumerate(time_metrics):
        x = 90 + index * 485
        draw.text((x, 1290), label, font=font(18), fill=muted)
        draw.text((x, 1330), value, font=font(28, True), fill=blue if index else orange)
        draw.text((x, 1385), note, font=font(16), fill=ink)
    draw.text((90, 1420), "閉鎖2時間は前回の同条件で約2時間54分。5時間上限まで約2時間06分の余裕。", font=font(18, True), fill=green)
    draw.text((90, 1460), "前回artifact時刻による実測です。区間ごとに速度は変わるため、今回の所要時間は保証されません。", font=font(17), fill=muted)

    box(draw, (55, 1545, 1545, 1795), pale_blue, blue, 3)
    draw.text((85, 1570), "成功したら、追加の物理計算なしでできること", font=font(27, True), fill=ink)
    draw.text((90, 1625), "1  不足中の時刻別結果9枚を補い、0%・100%を各5枚（合計10枚）にする", font=font(22, True), fill=blue)
    draw.text((90, 1675), "2  既存50%直接計算と、0%・100%から作る50:50補間を数値比較する", font=font(22, True), fill=blue)
    draw.text((90, 1725), "3  河口全域・河口堰・合流地点・魚道の直接／補間／誤差地図を作る", font=font(22, True), fill=blue)
    draw.text((90, 1765), "水深判定：平均的なずれ0.10m以下・最大0.25m以下（実水深精度ではなく補間の一致度）", font=font(17), fill=muted)

    box(draw, (55, 1845, 1545, 2120), pale_orange, orange, 3)
    draw.text((85, 1870), "残るリスク", font=font(27, True), fill=ink)
    draw.text((90, 1925), "• 短く分けても、計算速度低下やGitHub側の障害で停止する可能性があります。", font=font(21), fill=red)
    draw.text((90, 1973), "• 1区間が失敗すると残りを止め、自動やり直しはしません。使った計算時間は戻りません。", font=font(21), fill=red)
    draw.text((90, 2021), "• 完成しても、公開データと推論条件の検証です。実際の川との一致や当日予報は未証明です。", font=font(20), fill=ink)
    draw.text((90, 2069), "• 失敗後にもう一度実行する場合は、新しい判断と承認が必要です。", font=font(19), fill=ink)

    draw.text((55, 2170), "今回の判断", font=font(30, True), fill=ink)
    box(draw, (55, 2225, 1545, 2440), pale_blue, blue, 4, 20)
    draw.rounded_rectangle((85, 2255, 210, 2313), radius=14, fill=blue)
    draw.text((127, 2265), "A", font=font(28, True), fill=white)
    draw.text((245, 2255), "残り5区間を一回だけ実行する（推奨）", font=font(30, True), fill=ink)
    draw.text((90, 2335), "標準GitHub計算機だけを使い、成功後は検証・地図作成・結果記録まで進めます。", font=font(21), fill=ink)
    draw.text((90, 2385), "含まない：自動やり直し、別条件の物理計算、基準条件の次区間S03、一般公開、main反映", font=font(18, True), fill=blue)

    box(draw, (55, 2485, 1545, 2700), pale_orange, orange, 3, 20)
    draw.rounded_rectangle((85, 2515, 210, 2573), radius=14, fill=orange)
    draw.text((127, 2525), "B", font=font(28, True), fill=white)
    draw.text((245, 2515), "実行せず、判定不能のまま結果を保存する", font=font(28, True), fill=ink)
    draw.text((90, 2595), "追加料金・時間・実行リスクは発生しません。", font=font(20), fill=ink)
    draw.text((90, 2645), "既存の証拠は保存しますが、0%・100%から作る50%補間の精度は判断できません。", font=font(19), fill=muted)

    box(draw, (55, 2745, 1545, 2870), white, grey)
    draw.text((85, 2765), "Aの承認文面", font=font(20, True), fill=ink)
    draw.text((85, 2810), "承認済み河口堰holdout回復contract v1上で、閉鎖0%の2時間×4区間と開放100%の4時間×1区間を、", font=font(18, True), fill=blue)
    draw.text((85, 2845), "承認後24時間以内に一回限り実行してよい。", font=font(18, True), fill=blue)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=90, optimize=True, progressive=True)
    print(f"{output.relative_to(root)}\t{sha256(output)}\t{output.stat().st_size}")


if __name__ == "__main__":
    main()
