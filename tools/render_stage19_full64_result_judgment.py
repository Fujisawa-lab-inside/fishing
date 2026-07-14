#!/usr/bin/env python3
"""Create a labeled Stage 19 result judgment sheet from the five sealed maps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FONT_PATHS = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS:
        if Path(path).is_file():
            return ImageFont.truetype(path, size=size)
    raise RuntimeError("Japanese font required")


def rounded(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], fill: str, outline: str) -> None:
    draw.rounded_rectangle(bounds, radius=18, fill=fill, outline=outline, width=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="docs/results/stage19-full64-run-29323240389")
    parser.add_argument("--maps", default="docs/visuals/stage19-full64-results")
    parser.add_argument("--output", default="docs/visuals/stage19-full64-result-judgment.png")
    args = parser.parse_args()
    results, maps = Path(args.results), Path(args.maps)
    report = json.loads((results / "full64-report.json").read_text(encoding="utf-8"))
    manifest = json.loads((results / "full64-map-manifest.json").read_text(encoding="utf-8"))
    scale = {item["filename"]: item for item in manifest["maps"]}
    image = Image.new("RGB", (2100, 1850), "#f6f8f9")
    draw = ImageDraw.Draw(image)
    ink, muted, blue, orange, green = "#18313e", "#526b77", "#317086", "#a65231", "#28715f"

    draw.text((90, 55), "Stage 19 一回限りの実行結果", font=font(49), fill=ink)
    draw.text((90, 120), "数値安定性は合格。ただし500ステップは約3.25〜6.09秒です。",
              font=font(28), fill=muted)
    cards = [
        (90, "完了", "64 / 64", green),
        (710, "数値異常", "NaN 0・負水深 0", green),
        (1330, "最大値", "CFL 0.12・質量誤差 2.55×10⁻¹⁵", green),
    ]
    for x, label, value, color in cards:
        rounded(draw, (x, 185, x + 580, 300), "#ffffff", "#cad4da")
        draw.text((x + 24, 207), label, font=font(22), fill=muted)
        draw.text((x + 24, 246), value, font=font(27), fill=color)

    entries = [
        ("full64-depth-median.png", "水深中央値", "岸側が浅く、河道中央が深い形を確認"),
        ("full64-velocity-median.png", "流速中央値", "大部分は低速。強い変化は開境界付近"),
        ("full64-wet-probability.png", "湿潤確率", "大部分は64条件すべてで湿潤"),
        ("full64-direction-agreement.png", "流向一致度", "流れが生じた境界付近でのみ判定可能"),
        ("full64-direction-support.png", "流向サンプル率", "領域内部では有効な流向サンプルが少ない"),
    ]
    positions = [(90, 350), (750, 350), (1410, 350), (420, 970), (1080, 970)]
    for (filename, title, note), (x, y) in zip(entries, positions):
        rounded(draw, (x, y, x + 600, y + 570), "#ffffff", "#cad4da")
        draw.text((x + 22, y + 18), title, font=font(27), fill=ink)
        item = scale[filename]
        draw.text((x + 22, y + 58),
                  f"データ範囲 {item['dataMinimum']:.3g}〜{item['dataMaximum']:.3g} {item['units']}",
                  font=font(18), fill=muted)
        source = Image.open(maps / filename).convert("RGB")
        source.thumbnail((556, 382), Image.Resampling.LANCZOS)
        px = x + (600 - source.width) // 2
        image.paste(source, (px, y + 100))
        draw.text((x + 22, y + 505), note, font=font(19), fill=muted)

    rounded(draw, (90, 1585, 2010, 1735), "#fff4e9", "#d9a477")
    draw.text((125, 1610), "画像から判断すること", font=font(24), fill=orange)
    draw.text((125, 1655),
              "この結果を「数値安定性の証拠」として採用し、次に物理時間を定める設計へ進めるか",
              font=font(28), fill=ink)
    draw.text((90, 1778),
              "この画像だけで流速・流向の物理的妥当性は承認できません。追加実行・main反映・公開接続も含みません。",
              font=font(21), fill=muted)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG", optimize=True)
    print(json.dumps({"status": "rendered", "output": str(output), "width": 2100, "height": 1850}))


if __name__ == "__main__":
    main()
