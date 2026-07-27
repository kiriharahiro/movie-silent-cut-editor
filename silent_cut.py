import os
import sys
import re
import json
import subprocess
import argparse
import imageio_ffmpeg

__version__ = "v.00"

# 標準出力を UTF-8 に設定 (Windowsコンソールでのエンコーディングエラー防止)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def get_ffmpeg_exe():
    """imageio_ffmpegからFFmpegの実行ファイルパスを取得"""
    return imageio_ffmpeg.get_ffmpeg_exe()


def get_video_info(ffmpeg_exe, video_path):
    """
    FFmpegを使用して動画の総再生時間（秒）、フレームレート(fps)、解像度(width, height)を取得
    """
    cmd = [ffmpeg_exe, "-i", video_path]
    process = subprocess.Popen(
        cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore"
    )
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

    if duration == 0.0:
        raise ValueError("動画情報を取得できませんでした。ファイルパスや動画フォーマットを確認してください。")

    return {
        "duration": duration,
        "fps": fps,
        "width": width,
        "height": height
    }


def detect_silence(ffmpeg_exe, video_path, silence_thresh_db=-30.0, min_silence_len_sec=3.0):
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
    _, stderr = process.communicate()
    
    silence_periods = []
    current_start = None
    
    for line in stderr.splitlines():
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
                
    if current_start is not None:
        info = get_video_info(ffmpeg_exe, video_path)
        silence_periods.append((current_start, info["duration"]))
        
    return silence_periods


def calculate_keep_segments(silence_periods, total_duration, margin_sec=0.2):
    """
    無音区間から「残す区間（有音部分）」を厳密かつ精密に計算。
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


def generate_cut_video(ffmpeg_exe, input_path, keep_segments, output_mp4_path, fps=30.0):
    """
    FFmpegを使用して、無音部分を直接カット・結合したカット済み .mp4 動画ファイルを完全にリセットされたメタデータで自動出力します。
    """
    filter_complex_parts = []
    concat_inputs = []

    for idx, (start, end) in enumerate(keep_segments):
        filter_complex_parts.append(
            f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{idx}]; "
            f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{idx}]"
        )
        concat_inputs.append(f"[v{idx}][a{idx}]")

    concat_str = "".join(concat_inputs)
    filter_complex_str = (
        "; ".join(filter_complex_parts) +
        f"; {concat_str}concat=n={len(keep_segments)}:v=1:a=1[concatv][concata]; "
        f"[concatv]fps=fps={fps:.3f}[outv]; "
        f"[concata]aresample=async=1:first_pts=0[outa]"
    )

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
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_mp4_path
    ]

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore"
    )
    _, stderr = process.communicate()

    if process.returncode != 0 or not os.path.exists(output_mp4_path):
        raise RuntimeError(f"カット済み動画の完全再エンコード処理に失敗しました:\n{stderr}")

    return output_mp4_path


def generate_exo_project(video_path, keep_segments, output_exo_path, fps=30.0, width=1920, height=1080):
    """
    AviUtl拡張編集標準インポートフォーマット (.exo) を生成します。
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

    content = "\r\n".join(lines)

    try:
        with open(output_exo_path, "w", encoding="cp932", errors="replace") as f:
            f.write(content)
    except Exception:
        with open(output_exo_path, "w", encoding="utf-8") as f:
            f.write(content)

    return total_new_duration


def generate_aup2_project(video_path, keep_segments, output_aup2_path, fps=30.0, width=1920, height=1080):
    """
    AviUtl2用の .aup2 (JSON形式) プロジェクトファイルを生成
    """
    abs_video_path = os.path.abspath(video_path)
    
    timeline_objects = []
    current_timeline_time = 0.0

    for idx, (seg_start, seg_end) in enumerate(keep_segments):
        duration = seg_end - seg_start
        
        obj = {
            "id": idx + 1,
            "layer": 1,
            "start_time": round(current_timeline_time, 4),
            "duration": round(duration, 4),
            "type": "media",
            "file": abs_video_path,
            "source_start": round(seg_start, 4),
            "source_end": round(seg_end, 4),
            "has_video": True,
            "has_audio": True
        }
        timeline_objects.append(obj)
        current_timeline_time += duration

    aup2_data = {
        "format": "aup2",
        "version": "2.0",
        "project": {
            "width": width,
            "height": height,
            "framerate": fps,
            "sample_rate": 44100,
            "total_duration": round(current_timeline_time, 4),
            "object_count": len(timeline_objects)
        },
        "timeline": {
            "layers": [
                {"id": 1, "name": "Video/Audio 1"}
            ],
            "objects": timeline_objects
        }
    }

    with open(output_aup2_path, "w", encoding="utf-8") as f:
        json.dump(aup2_data, f, ensure_ascii=False, indent=2)

    return current_timeline_time


def main():
    parser = argparse.ArgumentParser(
        description=f"動画の無音部分を自動カットするツール ({__version__})"
    )
    parser.add_argument("-i", "--input", required=True, help="入力動画ファイル (.mp4)")
    parser.add_argument("-o", "--output", help="出力ファイルプレフィックス")
    parser.add_argument("-t", "--thresh", type=float, default=-30.0, help="無音判定レベル dB (デフォルト: -30.0)")
    parser.add_argument("-l", "--min-len", type=float, default=3.0, help="無音継続判定最小秒数 (デフォルト: 3.0)")
    parser.add_argument("-m", "--margin", type=float, default=0.2, help="のりしろ前後余白秒数 (デフォルト: 0.2)")
    parser.add_argument("--skip-mp4", action="store_true", help="無音カット済みMP4動画の生成をスキップ")
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

    print("==================================================")
    print(f" 🎬 動画無音自動カット ＆ 出力ツール {__version__}")
    print("==================================================")
    print(f"📁 入力ファイル : {input_path}")
    if not args.skip_mp4:
        print(f"📁 カット済みMP4 : {output_cut_mp4}")
    print(f"📁 出力EXO     : {output_exo}")
    print(f"📁 出力AUP2    : {output_aup2}")
    print(f"🔊 音声閾値    : {args.thresh} dB")
    print(f"⏱️ 最小無音時間: {args.min_len} 秒")
    print(f"✂️ のりしろ余白: {args.margin} 秒")
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

    if not args.skip_mp4:
        print("[3/4] 🎬 メタデータを完全リセットして MP4 動画を出力中...")
        generate_cut_video(ffmpeg_exe, input_path, keep_segments, output_cut_mp4, fps=fps)
        cut_info = get_video_info(ffmpeg_exe, output_cut_mp4)
        print(f"✨ カット済み MP4 の出力が完了しました！ (再生時間: {cut_info['duration']:.2f} 秒)")
    else:
        print("[3/4] 動画出力をスキップします")

    print("[4/4] AviUtlファイル (.exo & .aup2) を出力中...")
    new_duration = generate_exo_project(input_path, keep_segments, output_exo, fps=fps, width=width, height=height)
    generate_aup2_project(input_path, keep_segments, output_aup2, fps=fps, width=width, height=height)

    cut_time = total_duration - new_duration
    cut_ratio = (cut_time / total_duration) * 100 if total_duration > 0 else 0.0

    print("--------------------------------------------------")
    print("✅ 処理完了！")
    print(f"✂️ カット前総時間 : {total_duration:.2f} 秒")
    print(f"🎬 カット後総時間 : {new_duration:.2f} 秒")
    print(f"📉 削減時間       : {cut_time:.2f} 秒 ({cut_ratio:.1f}% カット)")
    if not args.skip_mp4:
        print(f"🎉 カット済みMP4   : {output_cut_mp4}")
    print(f"🎉 生成完了       : {output_exo}")
    print("==================================================")


if __name__ == "__main__":
    main()
