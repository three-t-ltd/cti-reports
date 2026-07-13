#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Instagramリール用 縦書きテロップ動画レンダラー。

JSON設定を受け取り、縦書きテロップPNGの生成 → ffmpegフィルタ構築 →
エンコードまでを一括で行う。

使い方:
    python3 render_reel.py config.json

設定例（すべての時刻は トリム後 のタイムライン秒）:
{
  "input": "/path/to/source.mp4",
  "output": "reel.mp4",
  "trim_start": 0.5,          // 省略可: 冒頭カット秒数（デフォルト 0）
  "duration": 15.7,           // 省略可: 出力尺。省略時は最後まで
  "telops": [
    {"text": "細長い製品の加工", "start": 0.0, "end": 1.5},
    {"text": "とにかく", "start": 4.0, "end": 4.8, "size": 145, "top_y": 260},
    {"text": "ツイジューソーチ", "start": 7.8, "end": 9.6, "style": "key",
     "swarm": {"count": 18}},
    {"text": "楽・楽", "start": 11.0, "end": 12.3, "style": "key", "size": 210}
  ]
}

テロップ仕様:
- 全て縦書き1列。「ー」「…」「（）」等は縦組み用に90度回転して描画する。
- style省略 or "normal": 白文字・画面左寄り(cx=290)・上から top_y(既定190)。
- style "key": 黄色・画面中央(cx=540)・上下センタリング・特大(既定size=150)。
- swarm: そのテロップの表示中、同じ文言の縦書きテロップを画面中に
  次々と湧き出させる（キメカット用の演出）。本体テロップは最前面を維持。
  オプション: count(既定18), interval(既定0.07), min_size(42), max_size(68), seed(11)
"""
import json
import os
import random
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]
W, H = 1080, 1920
WHITE = (255, 255, 255, 255)
YELLOW = (255, 217, 0, 255)
BLACK = (20, 20, 20, 255)
# 縦書きで90度回転させる文字
ROTATE_CHARS = set("ー…‥（）()「」『』［］[]｛｝{}～〜＝=－-")


def find_font(cfg):
    if cfg.get("font"):
        return cfg["font"]
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    sys.exit("日本語フォントが見つかりません。`sudo apt-get install -y fonts-noto-cjk` を実行してください。")


def char_tile(ch, size, fill, stroke_w, font_path):
    """1文字ぶんのタイル画像（縁取り付き、縦書き用回転対応）"""
    font = ImageFont.truetype(font_path, size)
    pad = stroke_w + 8
    tile = Image.new("RGBA", (size + pad * 2, size + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    bbox = d.textbbox((0, 0), ch, font=font)
    cw, chh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (tile.width - cw) / 2 - bbox[0]
    y = (tile.height - chh) / 2 - bbox[1]
    d.text((x, y), ch, font=font, fill=fill, stroke_width=stroke_w, stroke_fill=BLACK)
    if ch in ROTATE_CHARS:
        tile = tile.rotate(-90, resample=Image.BICUBIC)
    return tile


def vertical_word_image(text, size, fill, font_path, angle=0.0, pitch_ratio=1.03):
    """縦1列のワード画像（swarm用・回転可）"""
    stroke_w = max(4, int(size * 0.09))
    pitch = int(size * pitch_ratio)
    tiles = [char_tile(ch, size, fill, stroke_w, font_path) for ch in text]
    tw = max(t.width for t in tiles)
    th = pitch * (len(text) - 1) + tiles[-1].height
    img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    y = 0
    for t in tiles:
        img.alpha_composite(t, ((tw - t.width) // 2, y))
        y += pitch
    if angle:
        img = img.rotate(angle, expand=True, resample=Image.BICUBIC)
    return img


def make_telop_png(path, text, size, fill, cx, top_y, font_path, pitch_ratio=1.05):
    """フルフレーム(1080x1920)透過キャンバスにテロップを配置して保存"""
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    stroke_w = max(6, int(size * 0.085))
    pitch = int(size * pitch_ratio)
    total_h = pitch * (len(text) - 1) + size
    if top_y is None:  # 上下センタリング
        top_y = (H - total_h) / 2
    y = top_y
    for ch in text:
        tile = char_tile(ch, size, fill, stroke_w, font_path)
        canvas.alpha_composite(tile, (int(cx - tile.width / 2), int(y - (tile.height - size) / 2)))
        y += pitch
    canvas.save(path)


def make_swarm_pngs(workdir, text, opts, font_path):
    """湧き出し用ワードPNG群を生成し (path, x, y) を返す"""
    count = opts.get("count", 18)
    min_size = opts.get("min_size", 42)
    max_size = opts.get("max_size", 68)
    rng = random.Random(opts.get("seed", 11))
    # 縦長ワードなのでグリッド＋ジッターで敷き詰める
    n_cols = opts.get("cols", 6)
    n_rows = max(1, (count + n_cols - 1) // n_cols)
    cells = [(c, r) for c in range(n_cols) for r in range(n_rows)]
    rng.shuffle(cells)
    placements = []
    for i in range(count):
        c, r = cells[i % len(cells)]
        size = rng.randint(min_size, max_size)
        fill = YELLOW if i % 2 == 0 else WHITE
        angle = rng.uniform(-16, 16)
        img = vertical_word_image(text, size, fill, font_path, angle)
        cx = int((c + 0.5) * W / n_cols + rng.uniform(-45, 45))
        cy = int((r + 0.5) * H / n_rows + rng.uniform(-70, 70))
        x = max(-40, min(W - img.width + 40, cx - img.width // 2))
        y = max(-60, min(H - img.height + 60, cy - img.height // 2))
        path = os.path.join(workdir, f"swarm_{len(placements):03d}.png")
        img.save(path)
        placements.append((path, x, y))
    return placements


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    with open(sys.argv[1]) as f:
        cfg = json.load(f)

    font_path = find_font(cfg)
    workdir = cfg.get("workdir", "reel_work")
    os.makedirs(workdir, exist_ok=True)

    telops = cfg["telops"]
    end_time = cfg.get("duration") or max(t["end"] for t in telops)

    # 入力リストとオーバーレイ手順を構築
    inputs = []          # PNGパス（ffmpeg入力 1: 以降）
    steps = []           # (入力index, x, y, start, end)
    for ti, t in enumerate(telops):
        style = t.get("style", "normal")
        is_key = style == "key"
        size = t.get("size", 150 if is_key else 112)
        fill = YELLOW if is_key else WHITE
        cx = t.get("cx", 540 if is_key else 290)
        top_y = t.get("top_y", None if is_key else 190)

        # 湧き出しは本体より先にオーバーレイ（本体が最前面になる）
        if t.get("swarm"):
            sw = t["swarm"] if isinstance(t["swarm"], dict) else {}
            placements = make_swarm_pngs(workdir, t["text"], sw, font_path)
            t0 = t["start"] + sw.get("start_offset", 0.05)
            step = sw.get("interval", 0.07)
            for i, (path, x, y) in enumerate(placements):
                inputs.append(path)
                steps.append((len(inputs), x, y, round(t0 + i * step, 2), t["end"]))

        path = os.path.join(workdir, f"telop_{ti:02d}.png")
        make_telop_png(path, t["text"], size, fill, cx, top_y, font_path)
        inputs.append(path)
        steps.append((len(inputs), 0, 0, t["start"], t["end"]))

    # フィルタスクリプト
    lines = [f"[0:v]scale={W}:{H}:flags=lanczos[base];"]
    prev = "base"
    for n, (idx, x, y, a, b) in enumerate(steps):
        out = f"o{n}"
        lines.append(f"[{prev}][{idx}:v]overlay={x}:{y}:enable='between(t,{a},{b})'[{out}];")
        prev = out
    fade_in = cfg.get("fade_in", 0.25)
    fade_out = cfg.get("fade_out", 0.35)
    lines.append(
        f"[{prev}]fade=t=in:st=0:d={fade_in},"
        f"fade=t=out:st={round(end_time - fade_out, 2)}:d={fade_out}[vout]"
    )
    filter_path = os.path.join(workdir, "overlay.filter")
    with open(filter_path, "w") as f:
        f.write("\n".join(lines))

    # ffmpeg実行
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if cfg.get("trim_start"):
        cmd += ["-ss", str(cfg["trim_start"])]
    cmd += ["-t", str(end_time), "-i", cfg["input"]]
    for p in inputs:
        cmd += ["-i", p]
    cmd += ["-filter_complex_script", filter_path, "-map", "[vout]",
            "-c:v", "libx264", "-preset", "slow", "-crf", "19",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", cfg["output"]]
    subprocess.run(cmd, check=True)
    print(f"OK: {cfg['output']} ({end_time}s, {len(telops)} telops, {len(inputs)} overlays)")


if __name__ == "__main__":
    main()
