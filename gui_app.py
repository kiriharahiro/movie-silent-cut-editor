import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import time
import datetime
import json

# モジュールインポート
import silent_cut

# UTF-8設定
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


class TelopEditFrame(ttk.LabelFrame):
    """個別のテロップ（文言・座標・サイズ・拡大率）編集用フレーム"""
    def __init__(self, parent, title, config, update_callback):
        # 縦幅をコンパクトにするため padding を 4 に縮小
        super().__init__(parent, text=f" {title} ", padding=4)
        self.config = config
        self.update_callback = update_callback

        # 文言入力
        ttk.Label(self, text="テキスト:", font=("メイリオ", 8)).grid(row=0, column=0, sticky="w")
        self.var_text = tk.StringVar(value=config["text"])
        self.var_text.trace_add("write", self._on_change)
        entry_text = ttk.Entry(self, textvariable=self.var_text, width=24, font=("メイリオ", 8))
        entry_text.grid(row=0, column=1, columnspan=3, sticky="we", padx=(0, 5), pady=1)

        # X座標 / Y座標
        ttk.Label(self, text="X:", font=("メイリオ", 8)).grid(row=1, column=0, sticky="w")
        self.var_x = tk.IntVar(value=config["x"])
        self.var_x.trace_add("write", self._on_change)
        spin_x = ttk.Spinbox(self, from_=-2000, to=2000, increment=10, textvariable=self.var_x, width=6)
        spin_x.grid(row=1, column=1, sticky="w", pady=1)

        ttk.Label(self, text="Y:", font=("メイリオ", 8)).grid(row=1, column=2, sticky="w", padx=(5, 0))
        self.var_y = tk.IntVar(value=config["y"])
        self.var_y.trace_add("write", self._on_change)
        spin_y = ttk.Spinbox(self, from_=-2000, to=2000, increment=10, textvariable=self.var_y, width=6)
        spin_y.grid(row=1, column=3, sticky="w", pady=1)

        # フォントサイズ / 拡大率
        ttk.Label(self, text="サイズ:", font=("メイリオ", 8)).grid(row=2, column=0, sticky="w")
        self.var_size = tk.IntVar(value=config["size"])
        self.var_size.trace_add("write", self._on_change)
        spin_size = ttk.Spinbox(self, from_=10, to=300, increment=5, textvariable=self.var_size, width=6)
        spin_size.grid(row=2, column=1, sticky="w", pady=1)

        ttk.Label(self, text="拡大率(%):", font=("メイリオ", 8)).grid(row=2, column=2, sticky="w", padx=(5, 0))
        self.var_scale = tk.IntVar(value=config["scale"])
        self.var_scale.trace_add("write", self._on_change)
        spin_scale = ttk.Spinbox(self, from_=10, to=200, increment=5, textvariable=self.var_scale, width=6)
        spin_scale.grid(row=2, column=3, sticky="w", pady=1)

    def _on_change(self, *args):
        try:
            self.config["text"] = self.var_text.get()
            self.config["x"] = self.var_x.get()
            self.config["y"] = self.var_y.get()
            self.config["size"] = self.var_size.get()
            self.config["scale"] = self.var_scale.get()
        except Exception:
            pass
        self.update_callback()


class LogWindow(tk.Toplevel):
    """処理ログ表示専用の別ウィンドウ"""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("処理ログ")
        self.geometry("600x400")
        self.minsize(400, 300)
        self.parent = parent

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.log_text = tk.Text(self, wrap="word", font=("Consolas", 9))
        self.log_text.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        scrollbar = ttk.Scrollbar(self, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y", pady=5)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def on_close(self):
        self.parent.log_win = None
        self.destroy()


class SilentCutAppV01(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("動画無音自動カット ＆ 冒頭テロップ合成ツール v.01")
        # ログが別ウィンドウになったので、メインウィンドウの縦を 720 に縮小
        self.geometry("860x720")
        self.minsize(800, 680)

        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.telop_config = silent_cut.get_default_telop_config()
        self.video_info = {"width": 1920, "height": 1200, "fps": 25.0, "duration": 0.0}

        # プロセス管理とキャンセルフラグ
        self.current_process = None
        self.is_cancelled = False

        # ログ管理用
        self.log_win = None
        self.log_buffer = []

        # ドラッグ＆ドロップ移動用の変数
        self.dragged_telop = None
        self.drag_start_mx = 0
        self.drag_start_my = 0
        self.drag_start_tx = 0
        self.drag_start_ty = 0
        self.preview_scale = 1.0

        self.create_widgets()

        # 前回設定の自動ロード
        self.load_last_settings()

        # 登録済みプリセットのロード
        self.update_preset_list()

        # 終了時イベントのバインド
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        padding = {"padx": 10, "pady": 6}

        # 1. 動画ファイル選択 & 画角プロパティ表示
        file_frame = ttk.LabelFrame(self, text=" 1. 動画ファイルの選択 ＆ プロパティ ", padding=8)
        file_frame.pack(fill="x", **padding)

        self.path_var = tk.StringVar()
        entry = ttk.Entry(file_frame, textvariable=self.path_var, font=("メイリオ", 9))
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        btn_browse = ttk.Button(file_frame, text="参照...", command=self.browse_file)
        btn_browse.pack(side="right")

        self.lbl_info_var = tk.StringVar(value="画角サイズ: 未選択 | フレームレート: -- | 再生時間: --")
        lbl_info = ttk.Label(file_frame, textvariable=self.lbl_info_var, font=("メイリオ", 9, "bold"), foreground="#0066cc")
        lbl_info.pack(fill="x", pady=(5, 0))

        # 中央コンテンツ（テロップ編集 + プレビューキャンバス）
        middle_frame = ttk.Frame(self)
        middle_frame.pack(fill="both", expand=True, **padding)

        # 左側: テロップ＆無音設定
        left_pane = ttk.Frame(middle_frame)
        left_pane.pack(side="left", fill="y", padx=(0, 10))

        # テロップ1〜3の設定フレーム (pady=1で縦間隔を極限まで縮小)
        self.frame_t1 = TelopEditFrame(left_pane, "テロップ１ (上段)", self.telop_config["telop1"], self.update_preview)
        self.frame_t1.pack(fill="x", pady=1)

        self.frame_t2 = TelopEditFrame(left_pane, "テロップ２ (中段)", self.telop_config["telop2"], self.update_preview)
        self.frame_t2.pack(fill="x", pady=1)

        self.frame_t3 = TelopEditFrame(left_pane, "テロップ３ (下段)", self.telop_config["telop3"], self.update_preview)
        self.frame_t3.pack(fill="x", pady=1)

        # テロップフレーム連動用の辞書
        self.telop_frames = {
            "telop1": self.frame_t1,
            "telop2": self.frame_t2,
            "telop3": self.frame_t3
        }

        # ⚙️ テロッププリセット管理フレーム
        preset_frame = ttk.LabelFrame(left_pane, text=" ⚙️ テロッププリセットの管理 ", padding=6)
        preset_frame.pack(fill="x", pady=2)

        ttk.Label(preset_frame, text="保存名:", font=("メイリオ", 8)).grid(row=0, column=0, sticky="w")
        self.var_preset_name = tk.StringVar()
        entry_preset_name = ttk.Entry(preset_frame, textvariable=self.var_preset_name, width=16, font=("メイリオ", 8))
        entry_preset_name.grid(row=0, column=1, sticky="we", padx=(0, 5))

        btn_save_preset = ttk.Button(preset_frame, text="💾 保存", width=6, command=self.save_preset)
        btn_save_preset.grid(row=0, column=2, sticky="e")

        ttk.Label(preset_frame, text="プリセット:", font=("メイリオ", 8)).grid(row=1, column=0, sticky="w", pady=2)
        self.combo_preset = ttk.Combobox(preset_frame, width=15, state="readonly", font=("メイリオ", 8))
        self.combo_preset.grid(row=1, column=1, sticky="we", padx=(0, 5), pady=2)
        
        btn_load_preset = ttk.Button(preset_frame, text="📂 読込", width=6, command=self.load_preset)
        btn_load_preset.grid(row=1, column=2, sticky="e", pady=2)

        btn_delete_preset = ttk.Button(preset_frame, text="❌ 削除", width=6, command=self.delete_preset)
        btn_delete_preset.grid(row=2, column=2, sticky="e", pady=1)

        # 無音条件＆テロップ表示時間設定
        param_frame = ttk.LabelFrame(left_pane, text=" 無音条件 ＆ 表示時間 ", padding=6)
        param_frame.pack(fill="x", pady=2)

        ttk.Label(param_frame, text="テロップ表示時間(秒):", font=("メイリオ", 8)).grid(row=0, column=0, sticky="w")
        self.var_telop_dur = tk.DoubleVar(value=7.0)
        spin_telop_dur = ttk.Spinbox(param_frame, from_=1.0, to=30.0, increment=0.5, textvariable=self.var_telop_dur, width=6)
        spin_telop_dur.grid(row=0, column=1, sticky="w", pady=1)

        ttk.Label(param_frame, text="無音判定レベル(dB):", font=("メイリオ", 8)).grid(row=1, column=0, sticky="w")
        self.var_thresh = tk.DoubleVar(value=-30.0)
        spin_thresh = ttk.Spinbox(param_frame, from_=-60.0, to=0.0, increment=1.0, textvariable=self.var_thresh, width=6)
        spin_thresh.grid(row=1, column=1, sticky="w", pady=1)

        ttk.Label(param_frame, text="最小無音時間(秒):", font=("メイリオ", 8)).grid(row=2, column=0, sticky="w")
        self.var_min_len = tk.DoubleVar(value=3.0)
        spin_min_len = ttk.Spinbox(param_frame, from_=0.1, to=30.0, increment=0.5, textvariable=self.var_min_len, width=6)
        spin_min_len.grid(row=2, column=1, sticky="w", pady=1)

        ttk.Label(param_frame, text="のりしろ余白(秒):", font=("メイリオ", 8)).grid(row=3, column=0, sticky="w")
        self.var_margin = tk.DoubleVar(value=0.2)
        spin_margin = ttk.Spinbox(param_frame, from_=0.0, to=2.0, increment=0.05, textvariable=self.var_margin, width=6)
        spin_margin.grid(row=3, column=1, sticky="w", pady=1)

        ttk.Label(param_frame, text="開始時間(HH:MM:SS):", font=("メイリオ", 8)).grid(row=4, column=0, sticky="w")
        self.var_start_time = tk.StringVar(value="00:00:00")
        entry_start_time = ttk.Entry(param_frame, textvariable=self.var_start_time, width=10, font=("メイリオ", 8))
        entry_start_time.grid(row=4, column=1, sticky="w", pady=1)

        ttk.Label(param_frame, text="終了時間(HH:MM:SS):", font=("メイリオ", 8)).grid(row=4, column=2, sticky="w", padx=(10, 0))
        self.var_end_time = tk.StringVar(value="--:--:--")
        entry_end_time = ttk.Entry(param_frame, textvariable=self.var_end_time, width=10, font=("メイリオ", 8))
        entry_end_time.grid(row=4, column=3, sticky="w", pady=1)

        # テロップスタイル選択 (MeiryoUI 白字黒太枠 vs 黒字白太枠)
        ttk.Label(param_frame, text="テロップスタイル:", font=("メイリオ", 8)).grid(row=5, column=0, sticky="w", pady=1)
        self.var_telop_style = tk.StringVar(value="白文字＋黒太枠")
        self.combo_style = ttk.Combobox(param_frame, textvariable=self.var_telop_style, values=["白文字＋黒太枠", "黒文字＋白太枠"], state="readonly", width=14, font=("メイリオ", 8))
        self.combo_style.grid(row=5, column=1, columnspan=2, sticky="w", pady=1)
        self.combo_style.bind("<<ComboboxSelected>>", lambda e: self.update_preview())

        # 動画（MP4）出力の有無 (デフォルトは False = スキップ)
        self.var_generate_mp4 = tk.BooleanVar(value=False)
        self.chk_mp4 = ttk.Checkbutton(param_frame, text="カット済み動画(MP4)も一緒に出力する", variable=self.var_generate_mp4)
        self.chk_mp4.grid(row=6, column=0, columnspan=4, sticky="w", pady=2)

        # 右側: リアルタイムレイアウトプレビューキャンバス
        right_pane = ttk.LabelFrame(middle_frame, text=" 🖼️ 画面レイアウトプレビュー (画面配置確認) ", padding=8)
        right_pane.pack(side="right", fill="both", expand=True)

        self.canvas_width = 440
        self.canvas_height = 360
        self.canvas = tk.Canvas(right_pane, width=self.canvas_width, height=self.canvas_height, bg="#1e1e1e", highlightthickness=1, highlightbackground="#444")
        self.canvas.pack(fill="both", expand=True)

        # マウスドラッグ＆ドロップイベントのバインド (キャンバス全体)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        # 3. 実行・キャンセル・ログ表示ボタン
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=5)

        self.btn_run = ttk.Button(btn_frame, text="⚡ プレビューOK ➔ 無音カット ＆ テロップ合成を実行", command=self.start_process)
        self.btn_run.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.btn_cancel = ttk.Button(btn_frame, text="🛑 処理キャンセル", command=self.cancel_process, state="disabled")
        self.btn_cancel.pack(side="right", padx=(5, 5))

        # ログウィンドウを表示するボタン
        self.btn_log = ttk.Button(btn_frame, text="📋 ログ表示", command=self.show_log_window)
        self.btn_log.pack(side="right")

        # 進捗ステータス表示
        self.lbl_status_var = tk.StringVar(value="待機中")
        self.lbl_status = ttk.Label(self, textvariable=self.lbl_status_var, font=("メイリオ", 9, "bold"), foreground="#008800")
        self.lbl_status.pack(fill="x", padx=10, pady=(2, 5))

        self.update_preview()

    def on_canvas_click(self, event):
        """プレビュー上をクリックした時に、テロップ（重なり判定または近接距離判定）をドラッグ対象に選定する"""
        # 1. 直接ヒット判定（クリック座標の周囲8px範囲にテロップ要素があるか）
        x1, y1 = event.x - 8, event.y - 8
        x2, y2 = event.x + 8, event.y + 8
        overlapping_items = self.canvas.find_overlapping(x1, y1, x2, y2)
        
        # 手前に描画されているアイテムを優先してタグを判定
        for item_id in reversed(overlapping_items):
            tags = self.canvas.gettags(item_id)
            for key in ["telop1", "telop2", "telop3"]:
                if key in tags:
                    self.dragged_telop = key
                    self.drag_start_mx = event.x
                    self.drag_start_my = event.y
                    self.drag_start_tx = self.telop_config[key]["x"]
                    self.drag_start_ty = self.telop_config[key]["y"]
                    return

        # 2. フォールバック判定（マーカーの基準点からの距離測定。文字の外側などをクリックした場合）
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()

        if canvas_w < 50 or canvas_h < 50:
            canvas_w = self.canvas_width
            canvas_h = self.canvas_height

        vw = self.video_info.get("width", 1920)
        vh = self.video_info.get("height", 1200)

        # アスペクト比に合わせたスケール計算
        scale_x = (canvas_w - 40) / float(vw)
        scale_y = (canvas_h - 40) / float(vh)
        scale = min(scale_x, scale_y)

        disp_w = int(vw * scale)
        disp_h = int(vh * scale)

        offset_x = (canvas_w - disp_w) // 2
        offset_y = (canvas_h - disp_h) // 2

        min_dist = float("inf")
        target_key = None

        # 3つのテロップについて、クリック座標とマーカー(cx, cy)の距離をチェック
        for key in ["telop1", "telop2", "telop3"]:
            t_info = self.telop_config[key]
            text = t_info["text"]
            if not text:
                continue

            # AviUtl中央基準から絶対座標、およびプレビューキャンバス座標に変換
            fx, fy = silent_cut.aviutl_to_ffmpeg_coords(t_info["x"], t_info["y"], vw, vh)
            cx = offset_x + int(fx * scale)
            cy = offset_y + int(fy * scale)

            # マウスとのユーグリッド距離（2乗）
            dist = (event.x - cx) ** 2 + (event.y - cy) ** 2
            if dist < min_dist:
                min_dist = dist
                target_key = key

        # 最も近いテロップへの距離が80ピクセル（2乗で6400）以内であれば掴む
        if target_key and min_dist < 6400:
            self.dragged_telop = target_key
            self.drag_start_mx = event.x
            self.drag_start_my = event.y
            self.drag_start_tx = self.telop_config[target_key]["x"]
            self.drag_start_ty = self.telop_config[target_key]["y"]

    def on_canvas_drag(self, event):
        """プレビュー上をドラッグした時に座標を計算して更新する"""
        if not self.dragged_telop:
            return
        
        # マウス移動ピクセル
        dx_px = event.x - self.drag_start_mx
        dy_px = event.y - self.drag_start_my
        
        # プレビュー縮尺からAviUtl中央基準ピクセルに変換
        if self.preview_scale > 0:
            dx_aviutl = dx_px / self.preview_scale
            dy_aviutl = dy_px / self.preview_scale
            
            new_x = int(self.drag_start_tx + dx_aviutl)
            new_y = int(self.drag_start_ty + dy_aviutl)
            
            # 対応するテロップ編集スピンボックスのIntVarを更新する（自動で_on_changeが走り設定も同期される）
            frame = self.telop_frames[self.dragged_telop]
            frame.var_x.set(new_x)
            frame.var_y.set(new_y)

    def on_canvas_release(self, event):
        """ドラッグ終了時のリセット"""
        self.dragged_telop = None

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="動画ファイルを選択", filetypes=[("MP4動画", "*.mp4"), ("すべてのファイル", "*.*")]
        )
        if file_path:
            self.path_var.set(file_path)
            self.load_video_info(file_path)

    def load_video_info(self, file_path, auto_fill=True):
        try:
            ffmpeg_exe = silent_cut.get_ffmpeg_exe()
            info = silent_cut.get_video_info(ffmpeg_exe, file_path)
            self.video_info = info
            
            w, h = info["width"], info["height"]
            fps = info["fps"]
            dur = info["duration"]
            
            self.lbl_info_var.set(f"画角サイズ: {w} x {h} px (同一サイズ出力) | フレームレート: {fps:.2f} fps | 元再生時間: {dur:.1f} 秒")

            if auto_fill:
                # ファイル名からタイムスタンプ（日付）を自動抽出してテロップ3へセット
                date_str = silent_cut.extract_date_from_filename(file_path)
                self.frame_t3.var_text.set(date_str)

                # ファイル名からタイトルの自動補正（存在する場合）
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                if "ノンプロ研" in base_name or "勉強会" in base_name:
                    self.frame_t2.var_text.set(base_name)

            self.update_preview()

        except Exception as e:
            self.lbl_info_var.set(f"動画情報の取得エラー: {str(e)}")

    def update_preview(self):
        """キャンバス上に動画のアスペクト比枠とテロップ位置をリアルタイムプレビュー描画"""
        self.canvas.delete("all")

        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()

        if canvas_w < 50 or canvas_h < 50:
            canvas_w = self.canvas_width
            canvas_h = self.canvas_height

        vw = self.video_info.get("width", 1920)
        vh = self.video_info.get("height", 1200)

        # アスペクト比に合わせた画面スケール計算
        scale_x = (canvas_w - 40) / float(vw)
        scale_y = (canvas_h - 40) / float(vh)
        scale = min(scale_x, scale_y)
        self.preview_scale = scale  # 移動計算用に保存

        disp_w = int(vw * scale)
        disp_h = int(vh * scale)

        offset_x = (canvas_w - disp_w) // 2
        offset_y = (canvas_h - disp_h) // 2

        # 動画画面枠 of 描画
        self.canvas.create_rectangle(offset_x, offset_y, offset_x + disp_w, offset_y + disp_h, fill="#2b2b2b", outline="#666666", width=2)
        self.canvas.create_text(offset_x + 10, offset_y + 15, text=f"{vw}x{vh}", fill="#888888", font=("メイリオ", 8, "bold"), anchor="w")

        # テロップ1〜3の描画 (カラーはマーカー識別用)
        for key, color_code in [("telop1", "#ffcc00"), ("telop2", "#ffffff"), ("telop3", "#00ffcc")]:
            t_info = self.telop_config[key]
            text = t_info["text"]
            if not text:
                continue

            # AviUtl中央基準 (0,0) を FFmpeg/動画絶対座標 (0,0) に変換
            fx, fy = silent_cut.aviutl_to_ffmpeg_coords(t_info["x"], t_info["y"], vw, vh)

            # キャンバス上の描画座標へ変換
            cx = offset_x + int(fx * scale)
            cy = offset_y + int(fy * scale)

            # 拡大率反映フォントサイズ
            effective_size = int(t_info["size"] * (t_info["scale"] / 100.0) * scale)
            font_size = max(8, effective_size)

            # 影の太さを計算して太く描画する
            border_w = t_info.get("border_w", 4)
            effective_border_w = max(1, int(border_w * scale))

            # スタイルに応じた色決定
            try:
                style = self.var_telop_style.get()
            except AttributeError:
                style = "白文字＋黒太枠"

            if style == "黒文字＋白太枠":
                text_color = "#000000"
                border_color = "#ffffff"
            else:
                text_color = "#ffffff"
                border_color = "#000000"

            # 太い影を描く：周囲にピクセルをずらして複数回描画する
            for dx in range(-effective_border_w, effective_border_w + 1):
                for dy in range(-effective_border_w, effective_border_w + 1):
                    if dx != 0 or dy != 0:
                        self.canvas.create_text(cx + dx, cy + dy, text=text, fill=border_color, font=("メイリオ", font_size, "bold"), anchor="nw", tags=(key, "telop"))

            # 本文描画
            self.canvas.create_text(cx, cy, text=text, fill=text_color, font=("メイリオ", font_size, "bold"), anchor="nw", tags=(key, "telop"))

            # マーカー描画
            self.canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=color_code, outline="", tags=(key, "telop", "marker"))

    def log(self, message):
        """タイムスタンプ付きでバッファに保存し、別ウィンドウのテキストに表示する"""
        timestamp = datetime.datetime.now().strftime("[%H:%M:%S] ")
        full_msg = timestamp + message + "\n"
        self.log_buffer.append(full_msg)
        
        # バッファが大きくなりすぎないよう調整
        if len(self.log_buffer) > 2000:
            self.log_buffer.pop(0)

        # ログウィンドウが開いていればリアルタイムに追記
        if self.log_win is not None and self.log_win.winfo_exists():
            self.log_win.log_text.insert(tk.END, full_msg)
            self.log_win.log_text.see(tk.END)

    def show_log_window(self):
        """ログ表示ウィンドウを開き、前面に持ってくる"""
        if self.log_win is None or not self.log_win.winfo_exists():
            self.log_win = LogWindow(self)
            # 現在のバッファログを一括表示
            for msg in self.log_buffer:
                self.log_win.log_text.insert(tk.END, msg)
            self.log_win.log_text.see(tk.END)
        else:
            self.log_win.lift()
            self.log_win.focus_force()

    def save_log_file(self):
        """ログバッファの内容を logs フォルダ内の個別ログファイル（タイムスタンプ+テロップ1+テロップ2）に保管する"""
        if not self.log_buffer:
            return

        try:
            # 1. logs フォルダの自動作成
            base_dir = os.path.dirname(os.path.abspath(__file__))
            logs_dir = os.path.join(base_dir, "logs")
            os.makedirs(logs_dir, exist_ok=True)

            # 2. タイムスタンプの生成 (YYYYMMDD_HHMMSS)
            now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

            # 3. テロップ1, テロップ2 の取得とファイル名無害化 (サニタイズ)
            t1 = self.telop_config.get("telop1", {}).get("text", "").strip()
            t2 = self.telop_config.get("telop2", {}).get("text", "").strip()

            import re
            def sanitize_filename(name):
                # OSで禁止されている不整合文字を _ に置換
                clean = re.sub(r'[\\/:*?"<>|\r\n]', '_', name)
                return clean.strip()

            clean_t1 = sanitize_filename(t1)
            clean_t2 = sanitize_filename(t2)

            # ファイル名の組み立て (タイムスタンプ + テロップ1 + テロップ2)
            parts = [now_str]
            if clean_t1:
                parts.append(clean_t1)
            if clean_t2:
                parts.append(clean_t2)

            filename = "_".join(parts) + ".log"
            filepath = os.path.join(logs_dir, filename)

            # 4. ログファイルへの書き出し (UTF-8)
            with open(filepath, "w", encoding="utf-8") as f:
                f.writelines(self.log_buffer)

        except Exception as e:
            print(f"[LOG ERROR] ログの保管に失敗しました: {e}")

    def parse_time_to_seconds(self, time_str):
        """HH:MM:SS 形式の文字列を秒数に変換する"""
        parts = time_str.strip().split(':')
        if len(parts) != 3:
            raise ValueError("開始/終了時間は HH:MM:SS の形式で入力してください。")
        try:
            h = int(parts[0])
            m = int(parts[1])
            s = int(parts[2])
            val = h * 3600 + m * 60 + s
            if val < 0:
                raise ValueError()
            return val
        except Exception:
            raise ValueError("開始/終了時間には正の数値を指定してください。")

    def cancel_process(self):
        """現在実行中のプロセスがあれば停止する"""
        self.is_cancelled = True
        if self.current_process:
            try:
                self.current_process.terminate()
                self.log("🛑 プロセスに終了シグナルを送信しました。")
            except Exception as e:
                self.log(f"プロセス停止エラー: {str(e)}")

    def save_preset(self):
        """現在のテロップ設定を名前をつけて一括保存する"""
        name = self.var_preset_name.get().strip()
        if not name:
            messagebox.showerror("エラー", "保存するプリセット名を入力してください。")
            return
            
        preset_data = {
            "telop1": self.telop_config["telop1"].copy(),
            "telop2": self.telop_config["telop2"].copy(),
            "telop3": self.telop_config["telop3"].copy()
        }
        
        presets = {}
        if os.path.exists("telop_presets.json"):
            try:
                with open("telop_presets.json", "r", encoding="utf-8") as f:
                    presets = json.load(f)
            except:
                pass
                
        presets[name] = preset_data
        
        try:
            with open("telop_presets.json", "w", encoding="utf-8") as f:
                json.dump(presets, f, ensure_ascii=False, indent=2)
            self.update_preset_list()
            self.combo_preset.set(name)
            self.var_preset_name.set("")
            messagebox.showinfo("成功", f"プリセット '{name}' を保存しました。")
        except Exception as e:
            messagebox.showerror("エラー", f"プリセットの保存に失敗しました:\n{e}")

    def load_preset(self):
        """選択されたプリセットから設定を一括読込する"""
        name = self.combo_preset.get().strip()
        if not name:
            messagebox.showerror("エラー", "読み込むプリセットを選択してください。")
            return
            
        if not os.path.exists("telop_presets.json"):
            return
            
        try:
            with open("telop_presets.json", "r", encoding="utf-8") as f:
                presets = json.load(f)
            if name not in presets:
                messagebox.showerror("エラー", f"プリセット '{name}' が見つかりません。")
                return
                
            preset = presets[name]
            for key in ["telop1", "telop2", "telop3"]:
                if key in preset:
                    # UI変数を更新するだけで、trace_addにより自動的にself.telop_configが正しく同期される
                    frame = self.telop_frames[key]
                    p = preset[key]
                    frame.var_text.set(p.get("text", ""))
                    frame.var_x.set(p.get("x", 0))
                    frame.var_y.set(p.get("y", 0))
                    frame.var_size.set(p.get("size", 50))
                    frame.var_scale.set(p.get("scale", 100))
            
            self.update_preview()
            messagebox.showinfo("成功", f"プリセット '{name}' を読み込みました。")
        except Exception as e:
            messagebox.showerror("エラー", f"プリセットの読み込みに失敗しました:\n{e}")

    def delete_preset(self):
        """選択されたプリセットを削除する"""
        name = self.combo_preset.get().strip()
        if not name:
            return
        if not messagebox.askyesno("確認", f"プリセット '{name}' を削除しますか？"):
            return
        if not os.path.exists("telop_presets.json"):
            return
        try:
            with open("telop_presets.json", "r", encoding="utf-8") as f:
                presets = json.load(f)
            if name in presets:
                del presets[name]
                with open("telop_presets.json", "w", encoding="utf-8") as f:
                    json.dump(presets, f, ensure_ascii=False, indent=2)
                self.update_preset_list()
                self.combo_preset.set("")
                messagebox.showinfo("成功", f"プリセット '{name}' を削除しました。")
        except Exception as e:
            messagebox.showerror("エラー", f"プリセットの削除に失敗しました:\n{e}")

    def update_preset_list(self):
        """登録済みプリセットのリストを更新する"""
        if not os.path.exists("telop_presets.json"):
            self.combo_preset.config(values=[])
            return
        try:
            with open("telop_presets.json", "r", encoding="utf-8") as f:
                presets = json.load(f)
            names = list(presets.keys())
            self.combo_preset.config(values=names)
        except:
            self.combo_preset.config(values=[])

    def save_last_settings(self):
        """前回の設定値をlast_settings.jsonに保存する"""
        data = {
            "video_path": self.path_var.get(),
            "start_time": self.var_start_time.get(),
            "end_time": self.var_end_time.get(),
            "telop_dur": self.var_telop_dur.get(),
            "thresh": self.var_thresh.get(),
            "min_len": self.var_min_len.get(),
            "margin": self.var_margin.get(),
            "telop_style": self.var_telop_style.get(),
            "generate_mp4": self.var_generate_mp4.get(),
            "telop_config": self.telop_config
        }
        try:
            with open("last_settings.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def load_last_settings(self):
        """前回の設定値をlast_settings.jsonから復元する"""
        if not os.path.exists("last_settings.json"):
            return
        try:
            with open("last_settings.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.path_var.set(data.get("video_path", ""))
            self.var_start_time.set(data.get("start_time", "00:00:00"))
            self.var_end_time.set(data.get("end_time", "--:--:--"))
            self.var_telop_dur.set(data.get("telop_dur", 7.0))
            self.var_thresh.set(data.get("thresh", -30.0))
            self.var_min_len.set(data.get("min_len", 3.0))
            self.var_margin.set(data.get("margin", 0.2))
            self.var_telop_style.set(data.get("telop_style", "白文字＋黒太枠"))
            self.var_generate_mp4.set(data.get("generate_mp4", False))
            
            loaded_config = data.get("telop_config", {})
            for key in ["telop1", "telop2", "telop3"]:
                if key in loaded_config:
                    frame = self.telop_frames[key]
                    p = loaded_config[key]
                    frame.var_text.set(p.get("text", ""))
                    frame.var_x.set(p.get("x", 0))
                    frame.var_y.set(p.get("y", 0))
                    frame.var_size.set(p.get("size", 50))
                    frame.var_scale.set(p.get("scale", 100))
            
            p = self.path_var.get()
            if p and os.path.exists(p):
                # 自動ロード時は、日付・タイトルの自動抽出で上書きされないように auto_fill=False を指定
                self.load_video_info(p, auto_fill=False)
                
            self.update_preview()
        except Exception as e:
            print(f"Error loading settings: {e}")

    def on_closing(self):
        """アプリ終了時のイベント"""
        self.save_last_settings()
        if self.log_win is not None and self.log_win.winfo_exists():
            self.log_win.destroy()
        self.destroy()

    def start_process(self):
        input_path = self.path_var.get().strip()
        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("エラー", "有効な.mp4動画ファイルを選択してください。")
            return

        # 実行開始時の設定値を即時保存する（クラッシュ・強制終了対策）
        self.save_last_settings()

        # ログバッファをクリアし、ログ用別ウィンドウを自動で開く
        self.log_buffer.clear()
        self.show_log_window()
        if self.log_win and self.log_win.winfo_exists():
            self.log_win.log_text.delete("1.0", tk.END)

        self.btn_run.config(state="disabled")
        self.btn_cancel.config(state="normal")

        threading.Thread(target=self.run_process_thread, args=(input_path,), daemon=True).start()

    def run_process_thread(self, input_path):
        try:
            self.telop_config["duration"] = self.var_telop_dur.get()
            style_str = "black_on_white" if self.var_telop_style.get() == "黒文字＋白太枠" else "white_on_black"
            self.telop_config["style"] = style_str
            thresh = self.var_thresh.get()
            min_len = self.var_min_len.get()
            margin = self.var_margin.get()

            # 開始・終了時間の秒数
            cut_start_sec = self.parse_time_to_seconds(self.var_start_time.get())
            
            # 動画情報の取得を先に行う
            ffmpeg_exe = silent_cut.get_ffmpeg_exe()
            
            def set_proc(proc):
                self.current_process = proc

            self.log("[1/4] 動画情報を取得中...")
            video_info = silent_cut.get_video_info(ffmpeg_exe, input_path, on_process_created=set_proc)
            if self.is_cancelled:
                raise RuntimeError("ユーザーによりキャンセルされました。")

            total_duration = video_info["duration"]
            fps = video_info["fps"]
            width = video_info["width"]
            height = video_info["height"]
            self.log(f"⏱️ 動画サイズ: {width} x {height} px | FPS: {fps:.2f} | 時間: {total_duration:.2f} 秒")

            end_val = self.var_end_time.get().strip()
            if end_val == "" or end_val == "--:--:--":
                cut_end_sec = total_duration
            else:
                cut_end_sec = self.parse_time_to_seconds(end_val)

            if cut_start_sec > total_duration:
                raise ValueError(f"開始時間({self.var_start_time.get()})が動画の長さ({total_duration:.2f}秒)を超えています。")
            if cut_end_sec > total_duration:
                cut_end_sec = total_duration

            # 出力ファイル名の重複回避（連番を一貫させる）
            base, _ = os.path.splitext(input_path)
            target_mp4 = base + "_cut.mp4"
            if os.path.exists(target_mp4) or os.path.exists(base + ".exo"):
                counter = 1
                while True:
                    new_base = f"{base}_{counter:02d}"
                    if not os.path.exists(new_base + "_cut.mp4") and not os.path.exists(new_base + ".exo"):
                        base = new_base
                        break
                    counter += 1

            output_mp4 = base + "_cut.mp4"
            output_exo = base + ".exo"
            output_aup2 = base + ".aup2"

            self.log("==========================================")
            self.log(f" 🎬 動画無音自動カット ＆ テロップ合成")
            self.log("==========================================")
            self.log(f"📁 入力: {input_path}")
            self.log(f"⏱️ 指定時間範囲: {self.var_start_time.get()} ～ {self.var_end_time.get()} ({cut_start_sec} ～ {cut_end_sec} 秒)")
            self.log(f"📁 出力MP4: {output_mp4}")
            self.log(f"📁 出力EXO: {output_exo}")
            self.log(f"📁 出力AUP2: {output_aup2}")
            self.log(f"💬 テロップ1: {self.telop_config['telop1']['text']}")
            self.log(f"💬 テロップ2: {self.telop_config['telop2']['text']}")
            self.log(f"💬 テロップ3: {self.telop_config['telop3']['text']}")
            self.log("------------------------------------------")

            # 共通の進捗率・ETA計算用コールバックファクトリ
            def make_progress_callback(step_name):
                step_start_time = time.time()
                last_percent = [-1.0]
                def progress_cb(percent):
                    if percent - last_percent[0] < 1.0 and percent < 99.9:
                        return
                    last_percent[0] = percent
                    elapsed = time.time() - step_start_time
                    eta_str = "--:--"
                    if percent > 0:
                        total_est = elapsed / (percent / 100.0)
                        rem = max(0.0, total_est - elapsed)
                        eta_str = str(datetime.timedelta(seconds=int(rem)))
                    self.lbl_status_var.set(f"{step_name}: {percent:.1f}% (残り: {eta_str})")
                return progress_cb

            self.lbl_status_var.set("[2/4] 音声解析・無音検出中...")
            self.log("[2/4] 音声解析・無音検出を実行中...")
            progress_cb = make_progress_callback("[2/4] 音声解析中")
            silence_periods = silent_cut.detect_silence(
                ffmpeg_exe, input_path, thresh, min_len,
                on_process_created=set_proc, on_progress=progress_cb, total_duration=total_duration
            )
            if self.is_cancelled:
                raise RuntimeError("ユーザーによりキャンセルされました。")
            self.log(f"📊 検出された無音区間数: {len(silence_periods)} 箇所")

            keep_segments = silent_cut.calculate_keep_segments(silence_periods, total_duration, margin)
            self.log(f"✂️ 残す有音区間数: {len(keep_segments)} 箇所")

            # 開始・終了時間の指定範囲でフィルタリング
            filtered_segments = []
            for seg_start, seg_end in keep_segments:
                actual_start = max(seg_start, cut_start_sec)
                actual_end = min(seg_end, cut_end_sec)
                if actual_start < actual_end:
                    filtered_segments.append((actual_start, actual_end))
            keep_segments = filtered_segments
            self.log(f"✂️ 指定時間内の有音区間数: {len(keep_segments)} 箇所")

            if not keep_segments:
                raise ValueError("カットして残せる有音区間がありません。")

            if self.var_generate_mp4.get():
                self.log("[3/4] 🎬 無音カット＆冒頭テロップ合成 MP4 動画を出力中 (メタデータ完全リセット)...")
                self.lbl_status_var.set("[3/4] 動画出力中: 0.0%")
                progress_cb = make_progress_callback("[3/4] 動画出力中")
                
                silent_cut.generate_cut_video(
                    ffmpeg_exe, input_path, keep_segments, output_mp4,
                    fps=fps, width=width, height=height, telop_config=self.telop_config,
                    on_process_created=set_proc, on_progress=progress_cb
                )
                if self.is_cancelled:
                    raise RuntimeError("ユーザーによりキャンセルされました。")
                
                self.lbl_status_var.set("情報取得中...")
                cut_info = silent_cut.get_video_info(ffmpeg_exe, output_mp4, on_process_created=set_proc)
                self.log(f"✨ テロップ付きカット済み MP4 動画を出力完了！ (再生時間: {cut_info['duration']:.2f} 秒)")
            else:
                self.log("[3/4] 動画出力をスキップします（デフォルト）")

            self.log("[4/4] AviUtlファイル (.exo & .aup2) を出力中...")
            self.lbl_status_var.set("[4/4] プロジェクトファイル生成中...")
            new_duration = silent_cut.generate_exo_project(
                input_path, keep_segments, output_exo,
                fps=fps, width=width, height=height, telop_config=self.telop_config
            )
            silent_cut.generate_aup2_project(
                input_path, keep_segments, output_aup2,
                fps=fps, width=width, height=height, telop_config=self.telop_config,
                cut_video_path=output_mp4
            )

            cut_time = total_duration - new_duration
            cut_ratio = (cut_time / total_duration) * 100 if total_duration > 0 else 0.0

            self.log("------------------------------------------")
            self.log("✅ 処理が正常に完了しました！")
            self.log(f"✂️ カット前総時間 : {total_duration:.2f} 秒")
            self.log(f"🎬 カット後総時間 : {new_duration:.2f} 秒")
            self.log(f"📉 削減時間       : {cut_time:.2f} 秒 ({cut_ratio:.1f}% カット)")
            self.log(f"🎉 テロップ付きMP4 : {output_mp4}")
            self.log(f"🎉 生成完了       : {output_exo}")
            self.log("==========================================")

            self.lbl_status_var.set("処理完了！")

            # 完了ファンファーレ (ドミソド)
            try:
                import winsound
                winsound.Beep(523, 150)
                winsound.Beep(659, 150)
                winsound.Beep(784, 150)
                winsound.Beep(1047, 400)
            except Exception:
                pass

            msg = "処理が正常に完了しました！\n\n【出力ファイル】\n"
            if self.var_generate_mp4.get():
                msg += f"・カット済みMP4: {output_mp4}\n"
            msg += f"・AviUtl用オブジェクト: {output_exo}\n"
            msg += f"・AviUtl用プロジェクト: {output_aup2}\n\n"
            msg += "※ AviUtl2 で追加編集する場合は、上記 .aup2 プロジェクトファイルを開くか、または .exo ファイルをタイムラインへドラッグ＆ドロップしてください。"

            messagebox.showinfo("完了", msg)

        except Exception as e:
            self.lbl_status_var.set("エラー終了")
            if self.is_cancelled:
                self.log("\n🛑 処理がユーザーによりキャンセルされました。")
                messagebox.showinfo("キャンセル", "処理をキャンセルしました。")
            else:
                self.log(f"\n[エラー] 処理中にエラーが発生しました:\n{str(e)}")
                messagebox.showerror("処理エラー", str(e))

        finally:
            self.log("🏁 処理が終了しました。")
            self.save_log_file()
            self.btn_run.config(state="normal")
            self.btn_cancel.config(state="disabled")
            self.current_process = None
            self.is_cancelled = False


if __name__ == "__main__":
    app = SilentCutAppV01()
    app.mainloop()
