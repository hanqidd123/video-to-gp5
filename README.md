# Video TAB to GP5

A local Python command-line tool that reads visible six-string guitar tablature from static or page-changing videos and exports Guitar Pro 5 files. It also exports editable JSON with detected strings, frets, and OCR confidence.

## Windows setup

Install Python 3.11 and the Tesseract OCR engine. With both installed, run these commands in PowerShell from the project directory.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The script checks for Tesseract on PATH and in the standard Windows installation directory. Use `--tesseract` to specify a different executable.

## Convert a video

```powershell
.\.venv\Scripts\python.exe tab_converter.py "videos\input.mp4" -o "output\song.gp5"
```

You can also pass a YouTube URL you are authorized to download. The default crop covers the bottom 45% of the frame. Use `--roi LEFT TOP RIGHT BOTTOM` with normalized coordinates for other layouts. Run `--help` for sampling, timing, crop, and OCR options.

After editing the detected notes in the JSON, regenerate the GP5:

```powershell
.\.venv\Scripts\python.exe tab_converter.py "output\song.json" -o "output\song.gp5"
```

Review the frets and strings before using the result. The output defaults to 120 BPM and equal eighth notes in 4/4. The script does not recover the original rhythm, barlines, or playing techniques.
