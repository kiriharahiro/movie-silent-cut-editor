import subprocess
import imageio_ffmpeg

ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

# 10秒のテスト動画を作成（0-3秒: 440Hzトーン, 3-7秒: 無音, 7-10秒: 880Hzトーン）
cmd = [
    ffmpeg_exe,
    "-y",
    "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30",
    "-f", "lavfi", "-i", "sine=frequency=440:beep_factor=1:duration=3",
    "-f", "lavfi", "-i", "anullsrc=duration=4",
    "-f", "lavfi", "-i", "sine=frequency=880:beep_factor=1:duration=3",
    "-filter_complex", "[1:a][2:a][3:a]concat=n=3:v=0:a=1[a]",
    "-map", "0:v", "-map", "[a]",
    "-t", "10",
    "test_input.mp4"
]

print("テスト動画 test_input.mp4 を生成中...")
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode == 0:
    print("[OK] テスト動画 test_input.mp4 の作成に成功しました。")
else:
    print("[ERROR] エラーが発生しました:", res.stderr)
