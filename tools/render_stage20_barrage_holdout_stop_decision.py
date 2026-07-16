#!/usr/bin/env python3
"""Render the stopped barrage-holdout result and the next bounded decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from render_stage20_hypothetical_routing_preview import font


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def duration(value: float) -> str:
    hours = int(value // 3600)
    minutes = int(round((value - hours * 3600) / 60))
    if minutes == 60:
        hours += 1
        minutes = 0
    return f"{hours}時間{minutes:02d}分"


def draw_job_bar(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    width: int,
    wall_seconds: float | None,
    label: str,
    state: str,
    color: tuple[int, int, int],
) -> None:
    ink = (22, 47, 59)
    muted = (74, 95, 106)
    track = (221, 229, 232)
    draw.text((x, y), label, font=font(20, True), fill=ink)
    bar_y = y + 40
    draw.rounded_rectangle((x, bar_y, x + width, bar_y + 27), radius=13, fill=track)
    if wall_seconds is not None:
        value_width = max(8, min(width, int(width * wall_seconds / 18000)))
        draw.rounded_rectangle((x, bar_y, x + value_width, bar_y + 27), radius=13, fill=color)
        value = f"{duration(wall_seconds)}　{state}"
    else:
        value = state
    draw.text((x + width + 18, y + 34), value, font=font(18, True), fill=color if wall_seconds is not None else muted)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--analysis", default="config/stage20_barrage_holdout_analysis_v1.json")
    parser.add_argument("--output", default="docs/visuals/stage20-barrage-holdout-stop-decision.jpg")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    analysis = json.loads((root / args.analysis).read_text(encoding="utf-8"))
    completed = {item["jobId"]: item for item in analysis["completedSegments"]}
    stopped = analysis["stoppedSegment"]
    resource = analysis["resourceDiagnosis"]

    canvas = Image.new("RGB", (1600, 2520), (243, 247, 248))
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
    grey = (180, 195, 202)

    draw.text((55, 38), "河口堰holdout　5時間上限で停止", font=font(42, True), fill=ink)
    draw.text((55, 104), "run 29464186133／再実行なし／数値異常ではなく計算時間不足", font=font(22), fill=muted)

    draw.rounded_rectangle((55, 160, 1545, 445), radius=20, fill=white, outline=grey, width=2)
    metrics = [
        ("正常完了", "5／8 job", green),
        ("停止", "1 job", red),
        ("未実行", "2 job", orange),
        ("snapshot", "1／10", red),
    ]
    for index, (label, value, color) in enumerate(metrics):
        x = 90 + index * 360
        draw.text((x, 195), label, font=font(18), fill=muted)
        draw.text((x, 238), value, font=font(32, True), fill=color)
    draw.text(
        (90, 320),
        f"最大CFL {analysis['numericalSummary']['maximumCflAcrossCompletedSegments']:.2f}　　最大相対質量誤差 {analysis['numericalSummary']['maximumRelativeMassBalanceErrorAcrossCompletedSegments']:.2e}",
        font=font(23, True),
        fill=ink,
    )
    draw.text((90, 370), "非有限値 0　　負水深 0　　成功5 jobの全SHA-256と配列を検証済み", font=font(22, True), fill=green)

    draw.text((55, 495), "各区間の実計算時間（赤線＝5時間上限）", font=font(29, True), fill=ink)
    chart_x = 250
    chart_w = 1030
    cap_x = chart_x + chart_w
    draw.line((cap_x, 560, cap_x, 1130), fill=red, width=4)
    draw.text((cap_x - 55, 525), "5時間", font=font(17, True), fill=red)
    draw.text((55, 573), "開放100%", font=font(22, True), fill=blue)
    draw_job_bar(draw, x=chart_x, y=555, width=chart_w, wall_seconds=completed["barrage-open-s01"]["wallSeconds"], label="S01", state="完了", color=blue)
    draw_job_bar(draw, x=chart_x, y=660, width=chart_w, wall_seconds=completed["barrage-open-s02"]["wallSeconds"], label="S02", state="完了", color=blue)
    draw_job_bar(draw, x=chart_x, y=765, width=chart_w, wall_seconds=completed["barrage-open-s03"]["wallSeconds"], label="S03", state="完了", color=blue)
    draw_job_bar(draw, x=chart_x, y=870, width=chart_w, wall_seconds=None, label="S04", state="未実行", color=orange)
    draw.text((55, 993), "閉鎖0%", font=font(22, True), fill=orange)
    draw_job_bar(draw, x=chart_x, y=975, width=chart_w, wall_seconds=completed["barrage-closed-s01"]["wallSeconds"], label="S01", state="完了", color=orange)
    draw_job_bar(draw, x=chart_x, y=1080, width=chart_w, wall_seconds=completed["barrage-closed-s02"]["wallSeconds"], label="S02", state="完了", color=orange)

    draw.rounded_rectangle((55, 1195, 1545, 1455), radius=18, fill=pale_red, outline=red, width=3)
    draw.text((85, 1220), "停止した場所：閉鎖0% S03（−16→−12時間）", font=font(28, True), fill=red)
    draw.text((90, 1270), "外部制限5時間でexit 124。最後に保存できたのは3物理時間／4時間（75%）。", font=font(23, True), fill=ink)
    draw.text((90, 1320), f"3物理時間時点：計算 {duration(stopped['lastRetainedWallSeconds'])}、CFL {stopped['maximumCflAtLastCheckpoint']:.2f}、質量誤差 {stopped['maximumRelativeMassBalanceErrorAtLastCheckpoint']:.2e}", font=font(21), fill=ink)
    draw.text((90, 1370), f"同じ速度で4時間まで進む推計は {duration(resource['closedS03LinearFourHourProjectionWallSeconds'])}。上限を約{resource['closedS03LinearProjectionExcessOverLimitSeconds']/60:.0f}分超過。", font=font(21, True), fill=red)
    draw.text((90, 1413), "停止時artifactは未封印の診断資料。再開用の正式restartとしては扱いません。", font=font(18), fill=muted)

    draw.rounded_rectangle((55, 1500, 1545, 1745), radius=18, fill=pale_orange, outline=orange, width=3)
    draw.text((85, 1525), "今回まだ判断できないこと", font=font(28, True), fill=ink)
    draw.text((90, 1580), "0%・100%から作る50%補間が、50%直接計算と一致するか", font=font(25, True), fill=orange)
    draw.text((90, 1630), "必要な10 snapshotのうち1個だけ完成。補間値・誤差・4範囲地図は作成していません。", font=font(21), fill=ink)
    draw.text((90, 1680), "したがって補間は「不合格」ではなく「判定不能」です。", font=font(22, True), fill=red)

    draw.rounded_rectangle((55, 1790, 1545, 1975), radius=18, fill=white, outline=grey, width=2)
    draw.text((85, 1815), "再開前に直す必要があるもの", font=font(26, True), fill=ink)
    draw.text((90, 1870), "1  閉鎖条件の計算高速化、または安全な短区間化", font=font(21, True), fill=ink)
    draw.text((90, 1910), "2  4範囲セルmaskのSHA-256を実行前に固定", font=font(21, True), fill=ink)
    draw.text((790, 1910), "3  水深誤差の合否基準を追加", font=font(21, True), fill=ink)
    draw.text((90, 1950), "ここまでの準備はコードと計画だけ。追加の物理計算は別承認まで実行しません。", font=font(18), fill=muted)

    draw.text((55, 2020), "あなたが判断すること", font=font(30, True), fill=ink)
    draw.rounded_rectangle((55, 2075, 1545, 2265), radius=20, fill=pale_blue, outline=blue, width=4)
    draw.rounded_rectangle((85, 2105, 215, 2163), radius=14, fill=blue)
    draw.text((128, 2115), "A", font=font(28, True), fill=white)
    draw.text((245, 2105), "停止結果を採用し、高速化＋再開計画だけを作る（推奨）", font=font(29, True), fill=ink)
    draw.text((90, 2185), "コードだけで高速化を検証し、短区間のinactive contractを準備。物理runはまだ行いません。", font=font(20), fill=ink)
    draw.text((90, 2225), "既存の成功artifactと50% referenceは保持します。", font=font(18), fill=muted)

    draw.rounded_rectangle((55, 2305, 1545, 2435), radius=20, fill=pale_green, outline=green, width=3)
    draw.rounded_rectangle((85, 2335, 215, 2393), radius=14, fill=green)
    draw.text((128, 2345), "B", font=font(28, True), fill=white)
    draw.text((245, 2335), "結果を保存し、この検証を終了する", font=font(29, True), fill=ink)
    draw.text((90, 2395), "追加の準備・計算は行いません。", font=font(18), fill=muted)

    draw.text((55, 2470), "返信：A＝高速化と再開計画へ　／　B＝ここで終了", font=font(24, True), fill=ink)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=90, optimize=True, progressive=True)
    try:
        display_path = output.relative_to(root)
    except ValueError:
        display_path = output
    print(f"{display_path}\t{sha256(output)}\t{output.stat().st_size}")


if __name__ == "__main__":
    main()
