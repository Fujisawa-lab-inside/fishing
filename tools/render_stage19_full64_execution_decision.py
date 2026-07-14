#!/usr/bin/env python3
"""Render the one-decision Stage 19 full64 authorization sheet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FONT_PATHS = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
)


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS:
        if Path(path).is_file():
            return ImageFont.truetype(path, size=size)
    raise RuntimeError("a Japanese-capable font is required")


def rounded(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], fill: str, outline: str) -> None:
    draw.rounded_rectangle(bounds, radius=22, fill=fill, outline=outline, width=2)


def render(contract: dict, output: Path) -> None:
    image = Image.new("RGB", (2100, 1350), "#f6f8f9")
    draw = ImageDraw.Draw(image)
    ink, muted, blue, orange = "#18313e", "#526b77", "#317086", "#a65231"

    draw.text((110, 70), "次に判断すること：Stage 19 数値計算を1回実行するか", font=font(50), fill=ink)
    draw.text((110, 138), "入力統合と人工水路検証は完了。本番メッシュの時間更新はまだ0回です。",
              font=font(27), fill=muted)

    rounded(draw, (110, 215, 1990, 365), "#eaf3f5", "#9dbbc6")
    draw.text((155, 245), "承認すると実行する範囲", font=font(25), fill=blue)
    draw.text((155, 293), "64条件 × 500ステップ ＝ 32,000ステップを、一回限り実行",
              font=font(39), fill=ink)

    stages = [
        ("1", "本番メッシュ確認", "50,129セル\n時間更新 0回"),
        ("2", "数値計算", "64条件 × 500\n自動再試行なし"),
        ("3", "証拠を封印", "全数値・入力・\n停止理由を保存"),
        ("4", "判断用地図", "水深・流速など\n5枚を作成"),
    ]
    left, gap, width = 110, 35, 443
    for index, (number, title, detail) in enumerate(stages):
        x = left + index * (width + gap)
        rounded(draw, (x, 420, x + width, 630), "#ffffff", "#cad4da")
        draw.text((x + 28, 450), number, font=font(39), fill=blue)
        draw.text((x + 85, 454), title, font=font(27), fill=ink)
        draw.multiline_text((x + 30, 520), detail, font=font(24), fill=muted, spacing=10)
        if index < 3:
            draw.text((x + width + 5, 500), "→", font=font(31), fill="#7d9099")

    metrics = [
        (110, 675, 680, "見込み時間", "15〜30分", ink),
        (715, 675, 1285, "強制停止", "60分", orange),
        (1320, 675, 1990, "出力", "完全な数値証拠＋地図5枚", ink),
    ]
    for x1, y1, x2, label, value, value_color in metrics:
        rounded(draw, (x1, y1, x2, y1 + 105), "#ffffff", "#cad4da")
        draw.text((x1 + 28, y1 + 20), label, font=font(23), fill=muted)
        draw.text((x1 + 190, y1 + 17), value, font=font(31 if x2 - x1 < 600 else 27), fill=value_color)

    draw.text((110, 830), "実行時の主なリスク", font=font(28), fill=ink)
    risks = [
        "新しい計算核は人工水路では合格したが、本番計算は今回が初回",
        "水深・粗度・河川流量・堰・魚道は、観測値ではなく公開情報と推論の範囲",
        "M境界は博多の相対潮位を代理使用し、絶対標高とは接続していない",
        "数値基準を1つでも超えると停止し、5枚の地図が完成しない場合がある",
    ]
    for index, risk in enumerate(risks):
        y = 885 + index * 52
        draw.ellipse((126, y + 10, 140, y + 24), fill="#b16442")
        draw.text((160, y), risk, font=font(24), fill="#334d59")

    rounded(draw, (110, 1110, 1990, 1255), "#fff4e9", "#d9a477")
    draw.text((155, 1135), "必要な判断（二択）", font=font(24), fill="#94502f")
    draw.text((155, 1182), "実行してよい　／　今回は実行しない", font=font(40), fill=ink)
    draw.text((110, 1290),
              "この承認には main 反映・公開接続・物理的妥当性の承認は含まれません。承認しなければ現状で停止します。",
              font=font(21), fill="#667b85")

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", default="config/stage19_full64_execution_contract_v1.json")
    parser.add_argument("--output", default="docs/visuals/stage19-full64-execution-decision.png")
    args = parser.parse_args()
    contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    render(contract, Path(args.output))
    print(json.dumps({"status": "rendered", "output": args.output, "width": 2100, "height": 1350}))


if __name__ == "__main__":
    main()
