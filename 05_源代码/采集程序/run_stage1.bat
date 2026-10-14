@echo off
chcp 65001 >nul
cd /d %~dp0

rem 先跑这个！小规模试跑，几分钟就能看出你本机网络能不能通。
rem 优先用项目里的 .venv（就是你在 PyCharm 里建的那个解释器）；
rem 如果还没有 .venv，才退回用 PATH 上的 python。
set "PY=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"

echo 使用的解释器：%PY%
echo.

echo ================================================================
echo  试跑 1/3：只发现 200 部电影（约 1 分钟）
echo ================================================================
"%PY%" crawl.py discover --target 200 --max-pages 2
echo.
echo ================================================================
echo  试跑 2/3：只抓 10 部电影资料（约 1~2 分钟，一页里包含评分分布）
echo ================================================================
"%PY%" crawl.py movie --limit 10
echo.
echo ================================================================
echo  试跑 3/3：导出 CSV 到 export\ 目录
echo ================================================================
"%PY%" crawl.py export
echo.
echo 试跑完成。想跑全量（约 1000 部）就双击 run_all.bat。
pause
