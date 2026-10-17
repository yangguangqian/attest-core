@echo off
REM Seed the gltest direct-mode GenVM SDK cache.
REM Workaround for the upstream 404: gltest 0.29.2 looks for
REM genvm-universal.tar.xz, but genvm >= v0.3.0-rc7 ships genvm-runners-all.tar.xz.
REM Re-run this after a clean checkout or after upgrading genlayer-test.

set CACHE=%USERPROFILE%\.cache\gltest-direct
set VER=v0.3.0-rc7
set URL=https://github.com/genlayerlabs/genvm/releases/download/%VER%/genvm-runners-all.tar.xz

if not exist "%CACHE%" mkdir "%CACHE%"
if exist "%CACHE%\genvm-universal-%VER%.tar.xz" (
  echo already seeded
  exit /b 0
)

echo downloading %URL% ...
curl -L --retry 3 -o "%CACHE%\genvm-universal-%VER%.tar.xz" "%URL%"
echo done