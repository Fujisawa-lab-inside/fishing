#!/usr/bin/env python3
"""Render the Stage 20 mesh-v2/kernel-v2 one-time pilot decision."""

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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="docs/visuals/stage20-physical-pilot-v2-decision.jpg")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    benchmark = json.loads((root / "config/stage20_kernel_v2_synthetic_benchmark_v1.json").read_text(encoding="utf-8"))
    contract = json.loads((root / "config/stage20_physical_pilot_v2_contract_v1.json").read_text(encoding="utf-8"))

    old_minutes = benchmark["planningProjection"]["oldEstimatedWallSecondsFor600PhysicalSeconds"] / 60.0
    new_minutes = benchmark["planningProjection"]["projectedWallMinutesFor600PhysicalSeconds"]
    mesh_speedup = benchmark["speedup"]["meshV2VersusMeshV1"]
    kernel_speedup = benchmark["speedup"]["kernelV2VersusKernelV1OnMeshV2"]
    combined_speedup = benchmark["speedup"]["combinedV2VersusV1"]
    relative_difference = benchmark["equivalence"]["maximumRelativeStateDifference"]

    canvas = Image.new("RGB", (1800, 1420), (243, 247, 248))
    draw = ImageDraw.Draw(canvas)
    ink = (22, 47, 59)
    muted = (70, 94, 106)
    line = (195, 208, 214)
    blue = (16, 112, 174)
    green = (28, 130, 72)
    orange = (218, 126, 45)
    red = (177, 56, 46)

    draw.text((60, 38), "Stage 20　物理事前計算の高速化候補", font=font(47, True), fill=ink)
    draw.text((60, 101), "メッシュv2＋kernel v2／物理計算を実行せず、300ステップの合成試験で比較", font=font(24), fill=muted)

    draw.rounded_rectangle((50, 155, 1130, 720), radius=18, fill=(255, 255, 255), outline=line, width=2)
    draw.text((85, 190), "10分パイロットの計画時間", font=font(31, True), fill=ink)
    chart_x0, chart_x1 = 330, 1050
    bar_h = 82
    scale = (chart_x1 - chart_x0) / old_minutes
    rows = [
        ("旧v1実績からの推定", old_minutes, red, 300),
        ("v2高速化後の推定", new_minutes, green, 445),
    ]
    for label, value, colour, y in rows:
        draw.text((85, y + 18), label, font=font(24), fill=ink)
        draw.rounded_rectangle((chart_x0, y, chart_x1, y + bar_h), radius=12, fill=(232, 237, 239))
        width = max(8, round(value * scale))
        draw.rounded_rectangle((chart_x0, y, chart_x0 + width, y + bar_h), radius=12, fill=colour)
        value_text = f"{value:.1f}分"
        if value == old_minutes:
            # Keep the full reference value inside the chart card.
            draw.text((chart_x1 - 145, y + 17), value_text, font=font(27, True), fill=(255, 255, 255))
        else:
            draw.text((chart_x0 + width + 18, y + 17), value_text, font=font(27, True), fill=ink)
    cap_x = chart_x0 + 60.0 * scale
    draw.line((cap_x, 555, cap_x, 655), fill=orange, width=5)
    draw.text((cap_x + 12, 568), "停止上限60分", font=font(21, True), fill=orange)
    draw.text((85, 640), "約26分は合成試験の倍率を旧実績へ適用した推定で、実行結果ではありません。", font=font(21), fill=muted)

    draw.rounded_rectangle((1160, 155, 1750, 720), radius=18, fill=(255, 255, 255), outline=line, width=2)
    draw.text((1200, 190), "高速化の内訳", font=font(31, True), fill=ink)
    metrics = [
        ("メッシュv2", f"{mesh_speedup:.2f}倍"),
        ("kernel v2", f"{kernel_speedup:.2f}倍"),
        ("合計", f"{combined_speedup:.2f}倍"),
        ("300ステップ差", f"{relative_difference:.2e}"),
    ]
    y = 285
    for label, value in metrics:
        draw.text((1200, y), label, font=font(24), fill=muted)
        draw.text((1460, y), value, font=font(29, True), fill=green if label == "合計" else ink)
        y += 82
    draw.rounded_rectangle((1195, 610, 1715, 685), radius=12, fill=(231, 244, 235), outline=green, width=2)
    draw.text((1225, 629), "数値同一性：許容1e−12以内", font=font(23, True), fill=ink)

    draw.rounded_rectangle((50, 755, 1750, 1050), radius=18, fill=(255, 255, 255), outline=line, width=2)
    draw.text((85, 790), "今回承認する場合の実行範囲", font=font(31, True), fill=ink)
    scope = [
        "GitHub提供 Linux x86 runner／1条件だけ",
        "物理時間10分（600秒）／一回限り／承認後24時間以内",
        "最大60分で強制停止／自動再試行なし",
        "60秒ごとのチェックポイント／完了時に4地点の地図",
    ]
    y = 855
    for item in scope:
        draw.ellipse((88, y + 10, 102, y + 24), fill=blue)
        draw.text((122, y), item, font=font(25), fill=ink)
        y += 48
    draw.text((1000, 860), "停止条件", font=font(25, True), fill=red)
    stops = ["CFL超過", "負水深・異常値", "質量誤差超過", "60分到達"]
    y = 910
    for item in stops:
        draw.text((1005, y), f"・{item}", font=font(22), fill=muted)
        y += 36

    draw.rounded_rectangle((50, 1080, 1750, 1185), radius=16, fill=(252, 240, 228), outline=orange, width=3)
    draw.text((85, 1105), "リスク：実際の条件では約26分より遅く、60分で未完了停止する可能性があります。", font=font(26, True), fill=ink)
    draw.text((85, 1148), "推論入力の物理的正しさや36時間応答基底の妥当性は、この1回では確認できません。", font=font(21), fill=muted)

    draw.rounded_rectangle((50, 1215, 1750, 1365), radius=18, fill=(230, 243, 247), outline=blue, width=3)
    draw.text((85, 1245), "判断：この範囲で1条件×10分を一回だけ実行するか", font=font(32, True), fill=ink)
    draw.text((85, 1304), "A　実行する（推奨）", font=font(29, True), fill=ink)
    draw.text((840, 1304), "B　実行せず、コード高速化を続ける", font=font(29, True), fill=ink)
    draw.text((60, 1385), "Aを選ぶまではauthorizationとgateを作成せず、数値計算は開始しません。", font=font(18), fill=muted)

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=90, optimize=True, progressive=True)
    print(json.dumps({
        "status": "awaiting_one_time_physical_pilot_v2_decision",
        "output": args.output,
        "sha256": sha256(output),
        "oldProjectedMinutes": old_minutes,
        "newProjectedMinutes": new_minutes,
        "maximumWallMinutes": contract["run"]["maximumWallSeconds"] / 60.0,
        "physicalSolverExecuted": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
