# 🎬 動画無音自動カット ＆ AviUtl / MP4 出力ツール (v.00)

.mp4 動画の無音部分を自動で検出し、無音部分を取り除いたカット済み MP4 動画ファイル（`*_cut.mp4`）および AviUtl 用ファイル（`.exo` / `.aup2`）を出力するツールです。

---

## 📌 バージョン情報 (v.00 安定版)

- **バージョン**: `v.00` (初期フリーズ版)
- **主な特徴**:
  - FFmpeg による超高速・高精度な無音自動カット
  - VLC Player や一般プレイヤーでの 100% 正常再生（ヘッダーメタデータの完全リセット `-map_metadata -1` 適用済み）
  - MP4 動画直接出力（`*_cut.mp4`）＆ AviUtl / AviUtl2 互換 `.exo` / `.aup2` ファイル出力

---

## 💡 AviUtl / AviUtl2 での使用方法

1. **最も手軽な方法 (推奨)**
   - 生成された **`[動画名]_cut.mp4`** を AviUtl / AviUtl2 にドラッグ＆ドロップします。
   - 無音がカットされた状態の動画をすぐに編集いただけます。

2. **タイムラインオブジェクト (.exo) で読み込む方法**
   - AviUtl / AviUtl2 で「新規プロジェクトの作成」を行った状態で、生成された **`[動画名].exo`** をタイムラインにドラッグ＆ドロップ（または右クリックメニュー ➔「ファイル」➔「オブジェクトファイルを取り込み」）します。

---

## 🚀 使い方

### 1. GUI (画面) で使用する場合

```bash
python gui_app.py
```

### 2. コンソール (CLI) で使用する場合

```bash
python silent_cut.py -i 対象動画.mp4
```

---

## 📁 ファイル構成

- [silent_cut.py](file:///g:/共有ドライブ/KiriPlayPark/Tool/Antigravity/kiriplaypark-projects/movieEditor/silent_cut.py): 無音カット＆出力コアスクリプト (CLI)
- [gui_app.py](file:///g:/共有ドライブ/KiriPlayPark/Tool/Antigravity/kiriplaypark-projects/movieEditor/gui_app.py): GUI画面アプリケーション
- [VERSION](file:///g:/共有ドライブ/KiriPlayPark/Tool/Antigravity/kiriplaypark-projects/movieEditor/VERSION): バージョン表記ファイル (`v.00`)
