@echo off
rem 動画無音自動カット＆テロップ合成ツール 起動用バッチファイル
cd /d "%~dp0"

echo ツールを起動しています...
python gui_app.py

if %errorlevel% neq 0 (
    echo.
    echo 【エラー】アプリケーションが異常終了しました。
    echo 上記のエラーメッセージを確認してください。
    echo.
    pause
)
