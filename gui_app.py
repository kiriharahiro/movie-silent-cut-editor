import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# モジュールインポート
import silent_cut
import imageio_ffmpeg

# UTF-8設定
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


class SilentCutApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("動画無音自動カット ＆ AviUtl / MP4 出力ツール v.00")
        self.geometry("640x620")
        self.minsize(600, 540)

        # スタイル設定
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.create_widgets()

    def create_widgets(self):
        padding = {"padx": 15, "pady": 10}

        # 1. ファイル選択セクション
        file_frame = ttk.LabelFrame(self, text=" 1. 動画ファイルの指定 ", padding=10)
        file_frame.pack(fill="x", **padding)

        self.path_var = tk.StringVar()
        entry = ttk.Entry(file_frame, textvariable=self.path_var, font=("メイリオ", 9))
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        btn_browse = ttk.Button(file_frame, text="参照...", command=self.browse_file)
        btn_browse.pack(side="right")

        # 2. パラメータ設定セクション
        param_frame = ttk.LabelFrame(self, text=" 2. 無音カット条件の設定 ", padding=10)
        param_frame.pack(fill="x", **padding)

        # 無音判定レベル (dB)
        lbl_thresh = ttk.Label(param_frame, text="無音判定レベル (dB):", font=("メイリオ", 9))
        lbl_thresh.grid(row=0, column=0, sticky="w", pady=5)

        self.thresh_var = tk.DoubleVar(value=-30.0)
        spin_thresh = ttk.Spinbox(
            param_frame, from_=-60.0, to=0.0, increment=1.0, textvariable=self.thresh_var, width=10
        )
        spin_thresh.grid(row=0, column=1, sticky="w", padx=10, pady=5)
        ttk.Label(param_frame, text="(デフォルト: -30.0 dB / 小さい値ほど厳密)", font=("メイリオ", 8), foreground="gray").grid(
            row=0, column=2, sticky="w"
        )

        # 最小無音継続時間 (秒)
        lbl_min_len = ttk.Label(param_frame, text="最小無音継続時間 (秒):", font=("メイリオ", 9))
        lbl_min_len.grid(row=1, column=0, sticky="w", pady=5)

        self.min_len_var = tk.DoubleVar(value=3.0)
        spin_min_len = ttk.Spinbox(
            param_frame, from_=0.1, to=30.0, increment=0.5, textvariable=self.min_len_var, width=10
        )
        spin_min_len.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        ttk.Label(param_frame, text="(デフォルト: 3.0 秒)", font=("メイリオ", 8), foreground="gray").grid(
            row=1, column=2, sticky="w"
        )

        # のりしろ前後余白 (秒)
        lbl_margin = ttk.Label(param_frame, text="のりしろ余白 (秒):", font=("メイリオ", 9))
        lbl_margin.grid(row=2, column=0, sticky="w", pady=5)

        self.margin_var = tk.DoubleVar(value=0.2)
        spin_margin = ttk.Spinbox(
            param_frame, from_=0.0, to=2.0, increment=0.05, textvariable=self.margin_var, width=10
        )
        spin_margin.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        ttk.Label(param_frame, text="(デフォルト: 0.2 秒 / 頭切れ・尻切れ防止)", font=("メイリオ", 8), foreground="gray").grid(
            row=2, column=2, sticky="w"
        )

        # オプション: カット済みMP4動画の生成
        self.gen_mp4_var = tk.BooleanVar(value=True)
        chk_mp4 = ttk.Checkbutton(
            param_frame, text="無音カット済みの .mp4 動画ファイルも生成する (★推奨)", variable=self.gen_mp4_var
        )
        chk_mp4.grid(row=3, column=0, columnspan=3, sticky="w", pady=5)

        # 3. 実行ボタン
        self.btn_run = ttk.Button(self, text="⚡ 無音カットを実行 (MP4 / EXO / AUP2 生成)", command=self.start_process)
        self.btn_run.pack(fill="x", padx=15, pady=5)

        # 4. ログ出力エリア
        log_frame = ttk.LabelFrame(self, text=" 処理ログ ", padding=10)
        log_frame.pack(fill="both", expand=True, **padding)

        self.log_text = tk.Text(log_frame, wrap="word", font=("Consolas", 9), height=10)
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="動画ファイルを選択", filetypes=[("MP4動画", "*.mp4"), ("すべてのファイル", "*.*")]
        )
        if file_path:
            self.path_var.set(file_path)

    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def start_process(self):
        input_path = self.path_var.get().strip()
        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("エラー", "有効な.mp4動画ファイルを選択してください。")
            return

        self.btn_run.config(state="disabled")
        self.log_text.delete("1.0", tk.END)

        threading.Thread(target=self.run_process_thread, args=(input_path,), daemon=True).start()

    def run_process_thread(self, input_path):
        try:
            thresh = self.thresh_var.get()
            min_len = self.min_len_var.get()
            margin = self.margin_var.get()
            gen_mp4 = self.gen_mp4_var.get()

            base, _ = os.path.splitext(input_path)
            output_mp4 = base + "_cut.mp4"
            output_exo = base + ".exo"
            output_aup2 = base + ".aup2"

            self.log("==========================================")
            self.log(" 🎬 動画無音自動カット ＆ 高速処理")
            self.log("==========================================")
            self.log(f"📁 入力: {input_path}")
            if gen_mp4:
                self.log(f"📁 カット済みMP4: {output_mp4}")
            self.log(f"📁 出力EXO: {output_exo}")
            self.log(f"📁 出力AUP2: {output_aup2}")
            self.log(f"🔊 音声閾値: {thresh} dB")
            self.log(f"⏱️ 最小無音時間: {min_len} 秒")
            self.log(f"✂️ のりしろ余白: {margin} 秒")
            self.log("------------------------------------------")

            ffmpeg_exe = silent_cut.get_ffmpeg_exe()

            self.log("[1/4] 動画情報を取得中...")
            video_info = silent_cut.get_video_info(ffmpeg_exe, input_path)
            total_duration = video_info["duration"]
            fps = video_info["fps"]
            width = video_info["width"]
            height = video_info["height"]
            self.log(f"⏱️ 動画総再生時間: {total_duration:.2f} 秒 | FPS: {fps:.2f} | 解像度: {width}x{height}")

            self.log("[2/4] 音声解析・無音検出を実行中...")
            silence_periods = silent_cut.detect_silence(ffmpeg_exe, input_path, thresh, min_len)
            self.log(f"📊 検出された無音区間数: {len(silence_periods)} 箇所")

            keep_segments = silent_cut.calculate_keep_segments(silence_periods, total_duration, margin)
            self.log(f"✂️ 残す有音区間数: {len(keep_segments)} 箇所")

            if gen_mp4:
                self.log("[3/4] 🎬 無音カット済み MP4 動画を出力中 (終結処理を実行)...")
                silent_cut.generate_cut_video(ffmpeg_exe, input_path, keep_segments, output_mp4, fps=fps)
                self.log("✨ カット済み MP4 動画の終結処理が完了しました！")
            else:
                self.log("[3/4] MP4動画出力をスキップします。")

            self.log("[4/4] AviUtlファイル (.exo & .aup2) を出力中...")
            new_duration = silent_cut.generate_exo_project(
                input_path, keep_segments, output_exo, fps=fps, width=width, height=height
            )
            silent_cut.generate_aup2_project(
                input_path, keep_segments, output_aup2, fps=fps, width=width, height=height
            )

            cut_time = total_duration - new_duration
            cut_ratio = (cut_time / total_duration) * 100 if total_duration > 0 else 0.0

            self.log("------------------------------------------")
            self.log("✅ 処理が完了しました！")
            self.log(f"✂️ カット前総時間 : {total_duration:.2f} 秒")
            self.log(f"🎬 カット後総時間 : {new_duration:.2f} 秒")
            self.log(f"📉 削減時間       : {cut_time:.2f} 秒 ({cut_ratio:.1f}% カット)")
            if gen_mp4:
                self.log(f"🎉 カット済みMP4   : {output_mp4}")
            self.log(f"🎉 生成ファイル   : {output_exo}")
            self.log("==========================================")

            msg = (
                f"処理が正常に完了しました！\n\n"
                f"削減時間: {cut_time:.2f}秒 ({cut_ratio:.1f}%カット)\n\n"
            )
            if gen_mp4:
                msg += f"【おすすめの使い方】\n生成されたカット済み動画 `{output_mp4}` を AviUtl2 にドラッグ＆ドロップすると、無音カットされた状態の動画をすぐに編集できます！"
            else:
                msg += f"出力: {output_exo}"

            messagebox.showinfo("完了", msg)

        except Exception as e:
            self.log(f"\n[エラー] 処理中にエラーが発生しました:\n{str(e)}")
            messagebox.showerror("処理エラー", str(e))

        finally:
            self.btn_run.config(state="normal")


if __name__ == "__main__":
    app = SilentCutApp()
    app.mainloop()
