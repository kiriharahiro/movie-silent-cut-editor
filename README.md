# 🎬 動画編集自動化ツール群 (Movie Automation Suite)

動画の無音カット、AIによるフィラー・言い直し自動削除、冒頭テロップ合成を行い、AviUtl2 や DaVinci Resolve のタイムラインを瞬時に出力するツール群です。

---

## 📌 提供されている3つのツール

### 1. 🤖 [AI音声スマート編集ツール (`smart_editor/`)](smart_editor/README.md) ★最新・推奨
* **起動**: `smart_editor/run_app_smart.bat`
* **特徴**: Whisperによる文字起こし、**「フィラー（えー、あの等）削除」**、**「言い直し（重複・噛み直し）自動カット」**、無音カット、テロップ合成、AviUtl2（`.aup2`）＆ DaVinci Resolve（`.xml`）一括出力。

### 2. 🎬 [動画無音自動カット ＆ 冒頭テロップ合成ツールv.02 (ルート直下)](操作手順書_動画無音自動カット&冒頭テロップ合成ツール.md)
* **起動**: `run_app.bat`
* **特徴**: 高速な無音カット、**複数登壇LTの頭出しタグ付け ＆ 目次スプレッドシート連携（最小登壇時間可変・デフォルト120秒、スライド日本語OCR）**、AviUtl2（`.aup2`）、Premiere Pro / DaVinci Resolve / Filmora 共通（`.xml`）、字幕（`.srt`）一括出力、冒頭テロップ自動合成。

### 3. 🎞️ [DaVinci Resolve 向け 無音カット＆テロップ連携ツール (`davinci_resolve/`)](davinci_resolve/README_davinci.md)
* **起動**: `davinci_resolve/run_app_davinci.bat`
* **特徴**: DaVinci Resolve用 FCP7 XML タイムライン ＆ SRT字幕出力。

---

## 🚀 インストール方法
```bash
pip install imageio-ffmpeg faster-whisper
```

詳細な操作方法や機能比較は **[総合ドキュメント_動画編集自動化ツール群.md](総合ドキュメント_動画編集自動化ツール群.md)** をご覧ください。
