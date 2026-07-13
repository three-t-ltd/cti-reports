---
name: instagram-reel-edit
description: 素材動画からInstagramリール用ショート動画を編集する。縦書きテロップの焼き込み、キメ台詞の中央特大表示、テロップ湧き出し演出、9:16化・トリムまで一括対応。ユーザーが「リール」「ショート動画」「テロップ入れ」「Instagram用に編集」などを依頼したときに使用する。
---

# Instagramリール編集（縦書きテロップ）

素材動画（工場・現場系など）に縦書きテロップを載せて、テンポのよいリール動画に仕上げるワークフロー。町工場アカウント（例: 吉岡製作所 @yoshiokaseisakusyo）向けに確立したスタイル。

## 1. 環境準備

```bash
ffmpeg -version || sudo apt-get update && sudo apt-get install -y ffmpeg
fc-list | grep -q "Noto Sans CJK" || sudo apt-get install -y fonts-noto-cjk fonts-noto-cjk-extra
python3 -c "import PIL" || pip3 install pillow
```

## 2. 素材の入手

素材動画はクライアント共有のGoogle Driveフォルダに置かれる:
https://drive.google.com/drive/folders/1gtsVUuTTn64YIvfjasmujKI7d1TrmYPs

Google Drive MCPツールで取得する（チャット添付があればそちらを優先）:

1. `mcp__Google_Drive__search_files` で `parentId = '1gtsVUuTTn64YIvfjasmujKI7d1TrmYPs'` を検索
   （サブフォルダ「動画」= `1FmxkCE4NOKmcdPneUjthxK4kbax5EUno`、「画像」= `1d9zNTIU0Y3blsqV4B8OxhSWOSMNytovX` も同様に検索できる）
2. どの動画を使うか不明な場合は、ファイル名と更新日時を提示してユーザーに確認する（通常は最新のアップロードが対象）
3. `mcp__Google_Drive__download_file_content` でbase64を取得し、デコードして作業ディレクトリに保存:
   ```bash
   base64 -d encoded.txt > source.mp4
   ```

## 3. 素材の把握

1. `ffprobe` で解像度・尺・音声の有無を確認する。
2. 1fpsでフレームを抽出し、Readツールで**実際に見て**シーンを把握する:
   ```bash
   ffmpeg -y -i 素材.mp4 -vf "fps=1,scale=360:-1" frames/f_%02d.jpg
   ```
3. 「見せ場」（機械が動く瞬間、製品が持ち上がる瞬間など）が何秒にあるかをメモする。キメのテロップはここに合わせる。
4. 冒頭のカメラの傾き・手ブレ、末尾のブレは `trim_start` / `duration` でカットする。

## 4. テロップ構成のルール

- **丁寧語は使わない**。短いフレーズをテンポよく（1カット 0.8〜1.8秒、15秒で10〜11カットが目安）。
- 構成の型: 「課題の提示（あるある・ぼやき）→ 転機（そんな時にはコレ）→ 商品名・解決策（キメ）→ 効果 → 締め（お任せあれ等)」
- **全テロップ縦書き1列**（右から読む縦組み。改列はしない）。
- 通常テロップ: 白文字＋黒縁、画面**左寄り**（Instagram右側UIを回避）、上寄せ。
- **キメのテロップ**（商品名・決め台詞）: **黄色**・画面**中央**・**特大**・上下センタリング。
- キメには**湧き出し演出**（同じ文言の縦書きテロップが画面中に次々ポップする）を付けられる。ユーザーに提案してよい。
- 画面下部 約420px はInstagramのキャプション帯と重なるため長居させない（スクリプトの既定配置なら問題ない）。

## 5. レンダリング

`scripts/render_reel.py` に設定JSONを渡す。時刻はすべて**トリム後**のタイムライン秒。

```bash
python3 scripts/render_reel.py config.json
```

設定例（実案件で納品した構成）:

```json
{
  "input": "/path/to/source.mp4",
  "output": "reel_v1.mp4",
  "trim_start": 0.5,
  "duration": 15.7,
  "telops": [
    {"text": "細長い製品の加工",   "start": 0.0,  "end": 1.5},
    {"text": "振り回しが大変で",   "start": 1.5,  "end": 2.8},
    {"text": "腰折れも心配",       "start": 2.8,  "end": 4.0,  "size": 122, "top_y": 210},
    {"text": "とにかく",           "start": 4.0,  "end": 4.8,  "size": 145, "top_y": 260},
    {"text": "加工するのが憂鬱…", "start": 4.8,  "end": 6.4,  "size": 108, "top_y": 170},
    {"text": "そんな時にはコレ",   "start": 6.4,  "end": 7.8},
    {"text": "ツイジューソーチ",   "start": 7.8,  "end": 9.6,  "style": "key", "swarm": {"count": 18}},
    {"text": "少人数でも加工が",   "start": 9.6,  "end": 11.0},
    {"text": "楽・楽",             "start": 11.0, "end": 12.3, "style": "key", "size": 210},
    {"text": "大物・長物も",       "start": 12.3, "end": 14.0, "size": 122, "top_y": 210},
    {"text": "お任せあれ",         "start": 14.0, "end": 15.7, "size": 135, "top_y": 240}
  ]
}
```

サイズの目安: 8〜9文字は size 108〜115、6文字は 120〜125、4〜5文字は 135〜145。キメは 150（文字数が少なければ 200 超も可）。

## 6. 検証（必須）

各テロップの時間帯からフレームを抽出し、Readツールで**目視確認**する:

```bash
for t in 0.7 2.0 3.3 ... ; do ffmpeg -y -ss $t -i reel_v1.mp4 -frames:v 1 -vf scale=300:-1 check_$t.jpg; done
```

確認ポイント: 文字が画面内に収まっているか／「ー」「…」が縦組みになっているか／キメが中央に来ているか／被写体の見せ場をテロップが隠していないか。

## 7. 納品

- SendUserFile で mp4 を送る。
- 素材に音声がない場合はBGMなしで納品し、「Instagramアプリ内でトレンド音源を付けるとリーチが伸びる」と添える。
- 修正しやすいポイント（文言・タイミング・色・サイズ・演出の強弱）を箇条書きで提示する。

## 実装メモ

- ffmpegのdrawtextは縦書き非対応のため、Pillowで縦書きテロップPNGを生成して `overlay` で重ねる方式。
- 縦書きでは「ー」「…」「（）」等を90度回転させる必要がある（render_reel.py が対応済み）。
- 湧き出し演出は、小さな縦書きワードPNGを0.07秒間隔で `enable='between(t,開始,終了)'` によって順次表示している。本体のキメテロップは湧き出しの後にオーバーレイするため常に最前面。
- 乱数はシード固定（再現性があり、リテイク時も同じ配置になる）。配置を変えたいときは `swarm.seed` を変更する。
