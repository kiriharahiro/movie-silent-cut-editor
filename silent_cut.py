import os
import sys
import re
import json
import datetime
import subprocess
import argparse
import imageio_ffmpeg

__version__ = "v.01"

# 標準出力を UTF-8 に設定
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def get_ffmpeg_exe():
    """imageio_ffmpegからFFmpegの実行ファイルパスを取得"""
    return imageio_ffmpeg.get_ffmpeg_exe()


def extract_date_from_filename(filepath):
    """
    ファイル名から日付（YYYY.MM.DD）を自動抽出。
    例: GMT20260725-205522 -> 2026.07.25
    抽出できない場合はファイルの更新日時を使用。
    """
    filename = os.path.basename(filepath)
    match = re.search(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})", filename)
    if match:
        y, m, d = match.group(1), match.group(2), match.group(3)
        return f"{y}.{m}.{d}"
    
    # ファイルの作成/更新日時から取得
    try:
        mtime = os.path.getmtime(filepath)
        dt = datetime.datetime.fromtimestamp(mtime)
        return dt.strftime("%Y.%m.%d")
    except Exception:
        return "2026.07.25"


def get_video_info(ffmpeg_exe, video_path, on_process_created=None):
    """
    FFmpegを使用して動画の総再生時間（秒）、フレームレート(fps)、解像度(width, height)を取得
    """
    cmd = [ffmpeg_exe, "-i", video_path]
    process = subprocess.Popen(
        cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore"
    )
    if on_process_created:
        on_process_created(process)
    _, stderr = process.communicate()
    
    duration = 0.0
    fps = 30.0
    width, height = 1920, 1080

    match_dur = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", stderr)
    if match_dur:
        h, m, s = float(match_dur.group(1)), float(match_dur.group(2)), float(match_dur.group(3))
        duration = h * 3600 + m * 60 + s

    match_fps = re.search(r"(\d+(?:\.\d+)?)\s*(?:fps|tbr)", stderr)
    if match_fps:
        fps = float(match_fps.group(1))

    match_res = re.search(r"(\d{3,4})x(\d{3,4})", stderr)
    if match_res:
        width = int(match_res.group(1))
        height = int(match_res.group(2))

    audio_rate = 44100
    match_audio = re.search(r"Audio:.*?, (\d+) Hz", stderr)
    if match_audio:
        audio_rate = int(match_audio.group(1))

    if duration == 0.0:
        raise ValueError("動画情報を取得できませんでした。ファイルパスや動画フォーマットを確認してください。")

    return {
        "duration": duration,
        "fps": fps,
        "width": width,
        "height": height,
        "audio_rate": audio_rate
    }


def detect_silence(ffmpeg_exe, video_path, silence_thresh_db=-30.0, min_silence_len_sec=3.0, on_process_created=None, on_progress=None, total_duration=None):
    """
    FFmpegのsilencedetectフィルターを使用して無音区間を検出
    """
    cmd = [
        ffmpeg_exe,
        "-i", video_path,
        "-af", f"silencedetect=noise={silence_thresh_db}dB:d={min_silence_len_sec}",
        "-f", "null",
        "-"
    ]
    
    process = subprocess.Popen(
        cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore"
    )
    if on_process_created:
        on_process_created(process)
    
    silence_periods = []
    current_start = None
    
    # リアルタイムで標準エラー出力を読み取り
    while True:
        line = process.stderr.readline()
        if not line:
            break
        
        # 進捗計算
        if on_progress and total_duration and total_duration > 0:
            match_time = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
            if match_time:
                h, m, s = float(match_time.group(1)), float(match_time.group(2)), float(match_time.group(3))
                curr_t = h * 3600 + m * 60 + s
                progress = min(100.0, (curr_t / total_duration) * 100.0)
                on_progress(progress)
                
        # 無音区間の解析
        if "silence_start:" in line:
            match = re.search(r"silence_start:\s*([\d\.]+)", line)
            if match:
                current_start = float(match.group(1))
        elif "silence_end:" in line:
            match = re.search(r"silence_end:\s*([\d\.]+)", line)
            if match and current_start is not None:
                end_time = float(match.group(1))
                silence_periods.append((current_start, end_time))
                current_start = None
                
    process.wait()
                
    if current_start is not None:
        dur = total_duration if total_duration else get_video_info(ffmpeg_exe, video_path)["duration"]
        silence_periods.append((current_start, dur))
        
    return silence_periods


def calculate_keep_segments(silence_periods, total_duration, margin_sec=0.2):
    """
    無音区間から残す区間（有音部分）を計算
    """
    if not silence_periods:
        return [(0.0, total_duration)]

    keep_segments = []
    current_pos = 0.0

    for s_start, s_end in silence_periods:
        seg_end = min(total_duration, s_start + margin_sec)
        seg_start = max(current_pos, 0.0)

        if seg_end > seg_start + 0.05:
            keep_segments.append((seg_start, seg_end))

        current_pos = max(0.0, s_end - margin_sec)

    if current_pos < total_duration - 0.05:
        keep_segments.append((current_pos, total_duration))

    return keep_segments


def get_default_telop_config(filepath=""):
    """
    テロップのデフォルト設定を取得。
    """
    date_str = extract_date_from_filename(filepath) if filepath else "2026.07.25"
    return {
        "duration": 7.0,
        "style": "white_on_black",
        "telop1": {
            "text": "ノンプロ研",
            "x": -840,
            "y": 280,
            "size": 90,
            "scale": 80,
            "font": "メイリオ",
            "bold": True,
            "color": "white",
            "border_color": "black",
            "border_w": 4
        },
        "telop2": {
            "text": "イベントタイトル",
            "x": -890,
            "y": 376,
            "size": 120,
            "scale": 70,
            "font": "メイリオ",
            "bold": True,
            "color": "white",
            "border_color": "black",
            "border_w": 5
        },
        "telop3": {
            "text": date_str,
            "x": -840,
            "y": 480,
            "size": 50,
            "scale": 100,
            "font": "メイリオ",
            "bold": True,
            "color": "white",
            "border_color": "black",
            "border_w": 3
        }
    }


def aviutl_to_ffmpeg_coords(x_aviutl, y_aviutl, width=1920, height=1200):
    """
    AviUtl中央基準座標 (0,0) を FFmpeg 左上基準座標 (0,0) へ変換
    """
    ffmpeg_x = (width / 2.0) + x_aviutl
    ffmpeg_y = (height / 2.0) + y_aviutl
    return int(ffmpeg_x), int(ffmpeg_y)


def escape_ffmpeg_drawtext_text(text):
    """
    FFmpeg drawtext フィルター用に特殊文字をエスケープ
    """
    text = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "'\\\\''")
    return text


def build_drawtext_filters(telop_config, width, height):
    """
    テロップ1〜3の FFmpeg drawtext フィルター文字列を生成
    """
    duration = telop_config.get("duration", 7.0)
    font_path = "C\\:/Windows/Fonts/meiryob.ttc" if os.path.exists("C:/Windows/Fonts/meiryob.ttc") else "C\\:/Windows/Fonts/meiryo.ttc"
    
    # スタイル設定の取得
    style = telop_config.get("style", "white_on_black")
    if style == "black_on_white":
        fontcolor = "black"
        bordercolor = "white"
    else:
        fontcolor = "white"
        bordercolor = "black"

    drawtext_filters = []
    
    for key in ["telop1", "telop2", "telop3"]:
        t_info = telop_config[key]
        text = t_info["text"]
        if not text:
            continue
            
        esc_text = escape_ffmpeg_drawtext_text(text)
        
        # 拡大率を加味した実効フォントサイズ
        effective_size = int(t_info["size"] * (t_info["scale"] / 100.0))
        
        # 座標変換
        fx, fy = aviutl_to_ffmpeg_coords(t_info["x"], t_info["y"], width, height)
        
        border_w = t_info.get("border_w", 4)
        
        filter_str = (
            f"drawtext=fontfile='{font_path}':font='Meiryo':text='{esc_text}':"
            f"fontsize={effective_size}:fontcolor={fontcolor}:"
            f"bordercolor={bordercolor}:borderw={border_w}:"
            f"x={fx}:y={fy}:enable='between(t,0,{duration})'"
        )
        drawtext_filters.append(filter_str)

    return drawtext_filters


def generate_cut_video(ffmpeg_exe, input_path, keep_segments, output_mp4_path, fps=30.0, width=1920, height=1200, telop_config=None, on_process_created=None, on_progress=None):
    """
    FFmpegを使用して、無音カットおよび冒頭7秒間テロップを合成した MP4 動画を出力します。
    """
    # 古いインデックスファイルキャッシュ(.lwi)が残っているとL-SMASH Worksがロード失敗し続けるため、事前に削除します
    lwi_path = output_mp4_path + ".lwi"
    if os.path.exists(lwi_path):
        try:
            os.remove(lwi_path)
            print(f"[INFO] 古いインデックスファイルを削除しました: {lwi_path}")
        except Exception as e:
            print(f"[WARN] インデックスファイルの削除に失敗しました: {e}")

    filter_complex_parts = []
    concat_inputs = []

    for idx, (start, end) in enumerate(keep_segments):
        filter_complex_parts.append(
            f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{idx}]; "
            f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{idx}]"
        )
        concat_inputs.append(f"[v{idx}][a{idx}]")

    concat_str = "".join(concat_inputs)
    concat_output = (
        "; ".join(filter_complex_parts) +
        f"; {concat_str}concat=n={len(keep_segments)}:v=1:a=1[concatv][concata]"
    )

    # テロップフィルターの追加
    if telop_config:
        drawtext_list = build_drawtext_filters(telop_config, width, height)
        if drawtext_list:
            telop_chain = ", ".join(drawtext_list)
            filter_complex_str = f"{concat_output}; [concatv]{telop_chain}[telopv]; [telopv]fps=fps={fps:.3f}[outv]; [concata]aresample=async=1:first_pts=0[outa]"
        else:
            filter_complex_str = f"{concat_output}; [concatv]fps=fps={fps:.3f}[outv]; [concata]aresample=async=1:first_pts=0[outa]"
    else:
        filter_complex_str = f"{concat_output}; [concatv]fps=fps={fps:.3f}[outv]; [concata]aresample=async=1:first_pts=0[outa]"

    cmd = [
        ffmpeg_exe,
        "-y",
        "-fflags", "+genpts",
        "-i", input_path,
        "-filter_complex", filter_complex_str,
        "-map", "[outv]",
        "-map", "[outa]",
        "-map_metadata", "-1",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",  # 👈 L-SMASH Worksが認識できる超互換フォーマットに固定
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_mp4_path
    ]

    total_out_dur = sum(end - start for start, end in keep_segments)

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore"
    )
    if on_process_created:
        on_process_created(process)
        
    stderr_logs = []
    while True:
        line = process.stderr.readline()
        if not line:
            break
        stderr_logs.append(line)
        
        # 進捗計算
        if on_progress and total_out_dur > 0:
            match_time = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
            if match_time:
                h, m, s = float(match_time.group(1)), float(match_time.group(2)), float(match_time.group(3))
                curr_t = h * 3600 + m * 60 + s
                progress = min(100.0, (curr_t / total_out_dur) * 100.0)
                on_progress(progress)
                
    process.wait()
    stderr = "".join(stderr_logs)

    if process.returncode != 0 or not os.path.exists(output_mp4_path):
        raise RuntimeError(f"カット＆テロップ合成動画の出力に失敗しました:\n{stderr}")

    return output_mp4_path


def generate_exo_project(video_path, keep_segments, output_exo_path, fps=30.0, width=1920, height=1080, telop_config=None):
    """
    AviUtl拡張編集標準インポートフォーマット (.exo) を生成（テロップオブジェクト含む）
    """
    abs_video_path = os.path.abspath(video_path)
    
    total_new_duration = sum(end - start for start, end in keep_segments)
    total_frames = max(1, int(total_new_duration * fps))

    rate = int(round(fps))
    scale = 1
    if abs(fps - 29.97) < 0.1:
        rate = 30000
        scale = 1001
    elif abs(fps - 59.94) < 0.1:
        rate = 60000
        scale = 1001

    lines = []
    lines.append("[exedit]")
    lines.append(f"width={width}")
    lines.append(f"height={height}")
    lines.append(f"rate={rate}")
    lines.append(f"scale={scale}")
    lines.append(f"length={total_frames}")
    lines.append("audio_rate=44100")
    lines.append("audio_ch=2")
    lines.append("")

    current_frame = 1
    obj_idx = 0

    # 1. 映像・音声オブジェクトの追加
    for seg_start, seg_end in keep_segments:
        seg_duration = seg_end - seg_start
        frame_len = max(1, int(seg_duration * fps))
        end_frame = current_frame + frame_len - 1
        source_start_frame = max(1, int(seg_start * fps) + 1)

        lines.append(f"[{obj_idx}]")
        lines.append(f"start={current_frame}")
        lines.append(f"end={end_frame}")
        lines.append("layer=1")
        lines.append(f"group={obj_idx + 1}")
        lines.append("overlay=1")
        lines.append("camera=0")

        lines.append(f"[{obj_idx}.0]")
        lines.append("_name=動画ファイル")
        lines.append(f"再生位置={source_start_frame}")
        lines.append("再生速度=100.0")
        lines.append("ループ再生=0")
        lines.append("アルファチャンネルを読み込む=0")
        lines.append(f"file={abs_video_path}")

        lines.append(f"[{obj_idx}.1]")
        lines.append("_name=標準描画")

        obj_idx += 1

        lines.append(f"[{obj_idx}]")
        lines.append(f"start={current_frame}")
        lines.append(f"end={end_frame}")
        lines.append("layer=2")
        lines.append(f"group={obj_idx}")
        lines.append("overlay=1")
        lines.append("camera=0")

        lines.append(f"[{obj_idx}.0]")
        lines.append("_name=音声ファイル")
        lines.append(f"再生位置={source_start_frame}")
        lines.append("再生速度=100.0")
        lines.append("ループ再生=0")
        lines.append(f"file={abs_video_path}")

        lines.append(f"[{obj_idx}.1]")
        lines.append("_name=標準再生")

        obj_idx += 1
        current_frame = end_frame + 1

    # 2. テロップオブジェクトの追加 (Layer 3, 4, 5 に 冒頭7秒間)
    if telop_config:
        telop_frames = min(total_frames, int(telop_config.get("duration", 7.0) * fps))
        layer_num = 3
        
        # スタイルに応じた色設定
        style = telop_config.get("style", "white_on_black")
        if style == "black_on_white":
            text_color = "000000"
            border_color = "ffffff"
        else:
            text_color = "ffffff"
            border_color = "000000"

        for key in ["telop1", "telop2", "telop3"]:
            t_info = telop_config[key]
            text = t_info["text"]
            if not text:
                continue
                
            lines.append(f"[{obj_idx}]")
            lines.append("start=1")
            lines.append(f"end={telop_frames}")
            lines.append(f"layer={layer_num}")
            lines.append("group=0")
            lines.append("overlay=1")
            lines.append("camera=0")

            lines.append(f"[{obj_idx}.0]")
            lines.append("_name=テキスト")
            lines.append(f"サイズ={t_info['size']}")
            lines.append("表示速度=0.0")
            lines.append("文字毎に個別オブジェクト=0")
            lines.append("移動座標上に表示する=0")
            lines.append("自動折り返し=0")
            lines.append(f"font=メイリオ")
            lines.append(f"color={text_color}")
            lines.append(f"text={text}")

            lines.append(f"[{obj_idx}.1]")
            lines.append("_name=標準描画")
            lines.append(f"X={t_info['x']:.1f}")
            lines.append(f"Y={t_info['y']:.1f}")
            lines.append("Z=0.0")
            lines.append(f"拡大率={t_info['scale']:.1f}")
            lines.append("透明度=0.0")
            lines.append("回転=0.0")

            lines.append(f"[{obj_idx}.2]")
            lines.append("_name=縁取り")
            lines.append(f"サイズ={t_info.get('border_w', 4)}")
            lines.append(f"color={border_color}")

            obj_idx += 1
            layer_num += 1

    content = "\r\n".join(lines)

    try:
        with open(output_exo_path, "w", encoding="cp932", errors="replace") as f:
            f.write(content)
    except Exception:
        with open(output_exo_path, "w", encoding="utf-8") as f:
            f.write(content)

    return total_new_duration


def generate_aup2_project(video_path, keep_segments, output_aup2_path, fps, width, height, telop_config=None, cut_video_path=None):
    """有音カット済みの分割タイムライン構成を、完璧なAviUtl2形式(.aup2)で直接出力します。"""
    # ユーザー要望に基づき、カット済み動画ではなく、元動画を参照して多数の分割オブジェクトを配置します。
    abs_video_path = os.path.abspath(video_path).replace("/", "\\")
    abs_aup2_path = os.path.abspath(output_aup2_path).replace("/", "\\")

    # 音声レート取得
    try:
        ffmpeg_exe = get_ffmpeg_exe()
        video_info = get_video_info(ffmpeg_exe, video_path)
        audio_rate = video_info.get("audio_rate", 44100)
    except Exception:
        audio_rate = 44100

    # 有音カット後の総再生時間と総フレーム数を正確に算出
    total_new_duration = sum(end - start for start, end in keep_segments)
    total_frames = max(1, int(total_new_duration * fps))

    lines = []
    # 1. [project] セクション
    lines.append("[project]")
    lines.append("version=2001901")
    lines.append(f"ファイル={abs_aup2_path}")
    lines.append("display.scene=0")

    # 2. [scene.0] セクション
    lines.append("[scene.0]")
    lines.append("scene=0")
    lines.append("name=Root")
    lines.append(f"video.width={width}")
    lines.append(f"video.height={height}")
    lines.append(f"video.rate={int(round(fps))}")
    lines.append("video.scale=1")
    lines.append(f"audio.rate={audio_rate}")
    lines.append("cursor.frame=0")
    lines.append("cursor.layer=0")
    lines.append("display.frame=0")
    lines.append("display.layer=0")
    lines.append("display.zoom=10000")
    lines.append("display.order=0")
    lines.append("display.camera=")
    lines.append("display.grid.x=16,-16")
    lines.append("display.grid.y=16,-16")
    lines.append("display.grid.width=200")
    lines.append("display.grid.height=200")
    lines.append("display.grid.step=200.000000")
    lines.append("display.grid.range=10000.000000")
    lines.append("display.tempo.bpm=120.000000")
    lines.append("display.tempo.beat=4")
    lines.append("display.tempo.offset=0.000000")

    obj_id = 0
    current_frame = 0
    group_id = 1

    # 3. 有音区間（keep_segments）ごとに、映像（Layer 1）と音声（Layer 2）のオブジェクトを配置
    for seg_start, seg_end in keep_segments:
        seg_duration = seg_end - seg_start
        frame_len = max(1, int(seg_duration * fps))
        end_frame = current_frame + frame_len - 1

        # 映像オブジェクト (Layer 1)
        lines.append(f"[{obj_id}]")
        lines.append("layer=1")
        lines.append(f"frame={current_frame},{end_frame}")
        lines.append(f"group={group_id}")

        lines.append(f"[{obj_id}.0]")
        lines.append("effect.name=動画ファイル")
        lines.append(f"再生位置={seg_start:.2f}")
        lines.append("再生速度=100.00")
        lines.append("ループ再生=0.00")
        lines.append("アルファチャンネルを読み込む=0.00")
        lines.append(f"ファイル={abs_video_path}")

        lines.append(f"[{obj_id}.1]")
        lines.append("effect.name=標準描画")
        lines.append("X=0.00")
        lines.append("Y=0.00")
        lines.append("Z=0.00")
        lines.append("Group=1.00")
        lines.append("中心X=0.00")
        lines.append("中心Y=0.00")
        lines.append("中心Z=0.00")
        lines.append("X軸回転=0.00")
        lines.append("Y軸回転=0.00")
        lines.append("Z軸回転=0.00")
        lines.append("拡大率=100.00")
        lines.append("縦横比=0.00")
        lines.append("透明度=0.00")
        lines.append("合成モード=通常")

        obj_id += 1

        # 音声オブジェクト (Layer 2)
        lines.append(f"[{obj_id}]")
        lines.append("layer=2")
        lines.append(f"frame={current_frame},{end_frame}")
        lines.append(f"group={group_id}")

        lines.append(f"[{obj_id}.0]")
        lines.append("effect.name=音声ファイル")
        lines.append(f"再生位置={seg_start:.2f}")
        lines.append("再生速度=100.00")
        lines.append("ループ再生=0.00")
        lines.append("動画ファイルと連携=0.00")
        lines.append(f"ファイル={abs_video_path}")

        lines.append(f"[{obj_id}.1]")
        lines.append("effect.name=音声再生")
        lines.append("音量=100.00")
        lines.append("左右=0.00")

        obj_id += 1
        current_frame = end_frame + 1
        group_id += 1

    # 4. テロップオブジェクトの追加 (Layer 4, 5, 6)
    if telop_config:
        telop_frames = min(total_frames, int(telop_config.get("duration", 7.0) * fps))
        layer_num = 3 # Layer 4 (layer=3)

        # スタイルに応じた色設定
        style = telop_config.get("style", "white_on_black")
        if style == "black_on_white":
            text_color = "000000"
            border_color = "ffffff"
        else:
            text_color = "ffffff"
            border_color = "000000"

        for key in ["telop1", "telop2", "telop3"]:
            t_info = telop_config[key]
            text = t_info["text"]
            if not text:
                continue

            lines.append(f"[{obj_id}]")
            lines.append(f"layer={layer_num}")
            lines.append(f"frame=0,{telop_frames - 1}")

            # [obj_id.0] テキストエフェクト
            lines.append(f"[{obj_id}.0]")
            lines.append("effect.name=テキスト")
            lines.append(f"サイズ={float(t_info['size']):.2f}")
            lines.append("字間=0.00")
            lines.append("行間=0.00")
            lines.append("表示速度=0.00")
            lines.append(f"フォント=メイリオ")
            lines.append(f"文字色={text_color}")
            lines.append(f"影・縁色={border_color}")
            lines.append("文字装飾=標準文字")
            lines.append("文字揃え=左寄せ[上]")
            lines.append("B=1")
            lines.append("I=0")
            lines.append(f"テキスト={text}")
            lines.append("文字毎に個別オブジェクト=0")
            lines.append("自動スクロール=0")
            lines.append("移動座標上に表示=0")
            lines.append("オブジェクトの長さを自動調節=0")

            # [obj_id.1] 標準描画エフェクト
            lines.append(f"[{obj_id}.1]")
            lines.append("effect.name=標準描画")
            lines.append(f"X={float(t_info['x']):.2f}")
            lines.append(f"Y={float(t_info['y']):.2f}")
            lines.append("Z=0.00")
            lines.append("Group=1.00")
            lines.append("中心X=0.00")
            lines.append("中心Y=0.00")
            lines.append("中心Z=0.00")
            lines.append("X軸回転=0.00")
            lines.append("Y軸回転=0.00")
            lines.append("Z軸回転=0.00")
            lines.append(f"拡大率={float(t_info['scale']):.2f}")
            lines.append("縦横比=0.00")
            lines.append("透明度=0.00")
            lines.append("合成モード=通常")

            # [obj_id.2] 縁取りエフェクト
            lines.append(f"[{obj_id}.2]")
            lines.append("effect.name=縁取り")
            lines.append(f"サイズ={float(t_info.get('border_w', 4)):.2f}")
            lines.append("ぼかし=0.00")
            lines.append(f"縁色={border_color}")
            lines.append("パターン画像=")

            obj_id += 1
            layer_num += 1

    # 5. 保存 (改行コードCRLF、BOMなしUTF-8で書き出し)
    clean_content = "\r\n".join(lines) + "\r\n"
    try:
        with open(output_aup2_path, "wb") as f:
            f.write(clean_content.encode("utf-8"))
    except Exception as e:
        print(f"[WARN] .aup2ファイルの書き出し中にエラーが発生しました: {e}")

    return total_frames / fps


def main():
    parser = argparse.ArgumentParser(
        description=f"動画の無音部分を自動カットし冒頭7秒間テロップを合成するツール ({__version__})"
    )
    parser.add_argument("-i", "--input", required=True, help="入力動画ファイル (.mp4)")
    parser.add_argument("-o", "--output", help="出力ファイルプレフィックス")
    parser.add_argument("-t", "--thresh", type=float, default=-30.0, help="無音判定レベル dB (デフォルト: -30.0)")
    parser.add_argument("-l", "--min-len", type=float, default=3.0, help="無音継続判定最小秒数 (デフォルト: 3.0)")
    parser.add_argument("-m", "--margin", type=float, default=0.2, help="のりしろ前後余白秒数 (デフォルト: 0.2)")
    parser.add_argument("--telop1", default="ノンプロ研", help="テロップ1文言")
    parser.add_argument("--telop2", default="イベントタイトル", help="テロップ2文言")
    parser.add_argument("--telop3", help="テロップ3文言 (省略時は日付自動生成)")
    parser.add_argument("--generate-mp4", action="store_true", help="無音カット済みMP4動画を生成する（指定がない場合はスキップ）")
    parser.add_argument("--style", choices=["white_on_black", "black_on_white"], default="white_on_black", help="テロップスタイル (white_on_black: 白文字に黒枠, black_on_white: 黒文字に白枠)")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args()

    input_path = args.input
    if not os.path.exists(input_path):
        print(f"[エラー] 入力ファイルが見つかりません: {input_path}", file=sys.stderr)
        sys.exit(1)

    base, _ = os.path.splitext(input_path)
    output_cut_mp4 = base + "_cut.mp4"
    output_exo = base + ".exo"
    output_aup2 = base + ".aup2"

    telop_config = get_default_telop_config(input_path)
    if args.style:
        telop_config["style"] = args.style
    if args.telop1:
        telop_config["telop1"]["text"] = args.telop1
    if args.telop2:
        telop_config["telop2"]["text"] = args.telop2
    if args.telop3:
        telop_config["telop3"]["text"] = args.telop3

    print("==================================================")
    print(f" 🎬 動画無音自動カット ＆ テロップ合成ツール {__version__}")
    print("==================================================")
    print(f"📁 入力ファイル : {input_path}")
    if args.generate_mp4:
        print(f"📁 カット済みMP4 : {output_cut_mp4}")
    print(f"📁 出力EXO     : {output_exo}")
    print(f"📁 出力AUP2    : {output_aup2}")
    print(f"🔊 音声閾値    : {args.thresh} dB")
    print(f"⏱️ 最小無音時間: {args.min_len} 秒")
    print(f"✂️ のりしろ余白: {args.margin} 秒")
    print(f"💬 テロップ1   : {telop_config['telop1']['text']}")
    print(f"💬 テロップ2   : {telop_config['telop2']['text']}")
    print(f"💬 テロップ3   : {telop_config['telop3']['text']}")
    print("--------------------------------------------------")

    ffmpeg_exe = get_ffmpeg_exe()
    
    print("[1/4] 動画情報を取得中...")
    video_info = get_video_info(ffmpeg_exe, input_path)
    total_duration = video_info["duration"]
    fps = video_info["fps"]
    width = video_info["width"]
    height = video_info["height"]
    print(f"⏱️ 元動画再生時間: {total_duration:.2f} 秒 | FPS: {fps:.2f} | 解像度: {width}x{height}")

    print("[2/4] 音声解析・無音検出を実行中...")
    silence_periods = detect_silence(ffmpeg_exe, input_path, args.thresh, args.min_len)
    print(f"📊 検出された無音区間数: {len(silence_periods)} 箇所")

    keep_segments = calculate_keep_segments(silence_periods, total_duration, args.margin)
    print(f"✂️ 残す有音区間数: {len(keep_segments)} 箇所")

    if args.generate_mp4:
        print("[3/4] 🎬 無音カット＆冒頭テロップ合成 MP4 動画を出力中...")
        generate_cut_video(ffmpeg_exe, input_path, keep_segments, output_cut_mp4, fps=fps, width=width, height=height, telop_config=telop_config)
        cut_info = get_video_info(ffmpeg_exe, output_cut_mp4)
        print(f"✨ カット済み MP4 の出力が完了しました！ (再生時間: {cut_info['duration']:.2f} 秒)")
    else:
        print("[3/4] 動画出力をスキップします（デフォルト）")

    print("[4/4] AviUtlファイル (.exo & .aup2) を出力中...")
    new_duration = generate_exo_project(input_path, keep_segments, output_exo, fps=fps, width=width, height=height, telop_config=telop_config)
    generate_aup2_project(input_path, keep_segments, output_aup2, fps=fps, width=width, height=height, telop_config=telop_config, cut_video_path=output_cut_mp4)

    cut_time = total_duration - new_duration
    cut_ratio = (cut_time / total_duration) * 100 if total_duration > 0 else 0.0

    print("--------------------------------------------------")
    print("✅ 処理完了！")
    print(f"✂️ カット前総時間 : {total_duration:.2f} 秒")
    print(f"🎬 カット後総時間 : {new_duration:.2f} 秒")
    print(f"📉 削減時間       : {cut_time:.2f} 秒 ({cut_ratio:.1f}% カット)")
    if args.generate_mp4:
        print(f"🎉 カット済みMP4   : {output_cut_mp4}")
    print(f"🎉 生成完了       : {output_exo}")
    print("==================================================")


if __name__ == "__main__":
    main()
