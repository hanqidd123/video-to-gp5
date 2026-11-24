# Video TAB to GP5

从视频画面读取六弦吉他的六线谱，生成 Guitar Pro 5（`.gp5`）草稿和可编辑的音符 JSON。识别过程在本机运行。脚本适用于静态或翻页的谱面。

## Windows 本地安装

1. 安装 Git、Python 3.11 和 Tesseract OCR。已安装的组件可跳过。

   ```powershell
   winget install --id Git.Git --exact
   winget install --id Python.Python.3.11 --exact
   winget install --id UB-Mannheim.TesseractOCR --exact
   ```

2. 重新打开 PowerShell。使用有仓库访问权限的 GitHub 账号克隆项目。已有项目目录时，进入该目录即可。

   ```powershell
   git clone https://github.com/hanqidd123/video-to-gp5.git
   Set-Location video-to-gp5
   ```

3. 创建虚拟环境并安装依赖。已有可用的 `.venv` 时，可直接执行后两行。

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe tab_converter.py --help
   ```

脚本会从 PATH 或 Windows 默认安装路径查找 Tesseract。安装在其他位置时，在转换命令中加上 `--tesseract "C:\路径\tesseract.exe"`。

## 从视频生成草稿

```powershell
.\.venv\Scripts\python.exe tab_converter.py "videos\input.mp4" -o "output\song.gp5"
```

也可以把有权下载的 YouTube URL 作为输入。默认识别画面底部 45%。如果六线谱在上方，可用 `--roi LEFT TOP RIGHT BOTTOM` 设置比例坐标。项目样例使用以下参数：

```powershell
.\.venv\Scripts\python.exe tab_converter.py "videos\EeuIM1DBwas.mp4" --roi 0.055 0.145 0.99 0.398 --interval 0.5 -o "output\EeuIM1DBwas-draft.gp5"
```

每次转换同时生成 GP5 和 JSON。OCR 草稿默认使用 120 BPM、4/4 拍和等长八分音符。用 `--bpm` 和 `--duration` 调整草稿时值。原谱节奏、小节线、滑音和击勾弦需要额外校对。

## 修订和保存

改动音符 JSON 中的 `string` 和 `fret` 后，可以重新生成 GP5。若音符显式设置了 `"muted": true` 或 `"harmonic": true`，重新导出时会保留闷音或自然泛音。

```powershell
.\.venv\Scripts\python.exe tab_converter.py "output\song.json" -o "output\song.gp5"
```

如果已经在 Guitar Pro 中校正音符、节奏或技法，请直接保存为 Guitar Pro 原生 `.gp` 文件。需要旧版格式时，从 Guitar Pro 导出一份 GP5 并检查结果。项目样例的本地定稿为 `output/EeuIM1DBwas-final.gp`，来源是手动修订后的 `EeuIM1DBwas-techniques.gp`。源视频、中间文件和乐谱均保存在本地项目目录。
