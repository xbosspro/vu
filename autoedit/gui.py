"""Tkinter window for AutoEdit (opened from Resolve's Workspace > Scripts menu)."""

from __future__ import annotations

import os
import queue
import threading
import traceback
from typing import Optional

from .config import JobSettings
from .pipeline import analyze
from .planner import describe

SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".autoedit_resolve.json")
MODES = {"Theo nhịp (1 người, nhiều góc)": "rhythm",
         "Theo người nói (podcast, phỏng vấn)": "speaker",
         "Tắt": "off"}


def _load_last() -> JobSettings:
    try:
        return JobSettings.load(SETTINGS_FILE)
    except Exception:
        return JobSettings()


def main(resolve_hint: Optional[dict] = None) -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        print("Python này không có tkinter. Hãy dùng dòng lệnh: python -m autoedit --help")
        return

    job = _load_last()
    root = tk.Tk()
    root.title("AutoEdit cho DaVinci Resolve")
    root.geometry("760x720")
    pad = {"padx": 6, "pady": 3}

    # --- Inputs -------------------------------------------------------------
    files = ttk.LabelFrame(root, text="1. Nguồn")
    files.pack(fill="x", **pad)
    ttk.Label(files, text="Camera (camera 1 = góc chính):").grid(row=0, column=0, sticky="w")
    cam_list = tk.Listbox(files, height=4)
    cam_list.grid(row=1, column=0, columnspan=3, sticky="ew", padx=4)
    files.columnconfigure(1, weight=1)
    for c in job.cameras:
        if os.path.isfile(c):
            cam_list.insert("end", c)

    def add_cams():
        for p in filedialog.askopenfilenames(title="Chọn file camera"):
            cam_list.insert("end", p)

    def remove_cam():
        for i in reversed(cam_list.curselection()):
            cam_list.delete(i)

    btns = ttk.Frame(files)
    btns.grid(row=2, column=0, columnspan=3, sticky="w")
    ttk.Button(btns, text="Thêm camera...", command=add_cams).pack(side="left", padx=2)
    ttk.Button(btns, text="Xoá", command=remove_cam).pack(side="left", padx=2)

    def path_row(row, label, value, is_dir=False, types=None):
        var = tk.StringVar(value=value or "")
        ttk.Label(files, text=label).grid(row=row, column=0, sticky="w")
        ttk.Entry(files, textvariable=var).grid(row=row, column=1, sticky="ew", padx=4)

        def browse():
            p = (filedialog.askdirectory() if is_dir
                 else filedialog.askopenfilename(filetypes=types or []))
            if p:
                var.set(p)
        ttk.Button(files, text="...", width=3, command=browse).grid(row=row, column=2)
        return var

    audio_var = path_row(3, "Âm thanh rời (tuỳ chọn):", job.audio)
    broll_var = path_row(4, "Thư mục B-roll (tuỳ chọn):", job.broll_dir, is_dir=True)
    srt_var = path_row(5, "Phụ đề .srt (tuỳ chọn):", job.srt,
                       types=[("Subtitles", "*.srt"), ("All", "*.*")])
    name_var = tk.StringVar(value=job.timeline_name)
    ttk.Label(files, text="Tên timeline:").grid(row=6, column=0, sticky="w")
    ttk.Entry(files, textvariable=name_var).grid(row=6, column=1, sticky="ew", padx=4)

    # --- Settings -----------------------------------------------------------
    def num_row(frame, row, label, value):
        var = tk.StringVar(value="" if value is None else str(value))
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w")
        ttk.Entry(frame, textvariable=var, width=10).grid(row=row, column=1, sticky="w")
        return var

    opts = ttk.Frame(root)
    opts.pack(fill="x", **pad)
    sil = ttk.LabelFrame(opts, text="2. Cắt khoảng lặng")
    sil.pack(side="left", fill="both", expand=True, padx=3)
    thr_var = num_row(sil, 0, "Ngưỡng im lặng (dB)", job.silence.threshold_db)
    mins_var = num_row(sil, 1, "Lặng tối thiểu (s)", job.silence.min_silence)
    padd_var = num_row(sil, 2, "Chừa đệm (s)", job.silence.padding)

    cam = ttk.LabelFrame(opts, text="3. Đảo góc máy")
    cam.pack(side="left", fill="both", expand=True, padx=3)
    mode_var = tk.StringVar(value=next(k for k, v in MODES.items() if v == job.multicam.mode))
    ttk.Combobox(cam, textvariable=mode_var, values=list(MODES), state="readonly",
                 width=32).grid(row=0, column=0, columnspan=2, sticky="w")
    wide = job.multicam.wide_camera
    wide_var = num_row(cam, 1, "Camera toàn cảnh số", None if wide is None else wide + 1)
    minshot_var = num_row(cam, 2, "Shot ngắn nhất (s)", job.multicam.min_shot)
    maxshot_var = num_row(cam, 3, "Shot dài nhất (s)", job.multicam.max_shot)
    sync_var = tk.BooleanVar(value=job.multicam.sync == "audio")
    ttk.Checkbutton(cam, text="Tự đồng bộ theo sóng âm", variable=sync_var).grid(
        row=4, column=0, columnspan=2, sticky="w")

    br = ttk.LabelFrame(opts, text="4. B-roll")
    br.pack(side="left", fill="both", expand=True, padx=3)
    br_on = tk.BooleanVar(value=job.broll.enabled)
    ttk.Checkbutton(br, text="Chèn B-roll", variable=br_on).grid(row=0, column=0, sticky="w")
    fill_var = tk.BooleanVar(value=job.broll.fill)
    ttk.Checkbutton(br, text="Rải đều (ngoài từ khoá)", variable=fill_var).grid(
        row=1, column=0, columnspan=2, sticky="w")
    int_var = num_row(br, 2, "Cách nhau (s)", job.broll.interval)
    dur_var = num_row(br, 3, "Dài mỗi đoạn (s)", job.broll.duration)

    # --- Log + run ----------------------------------------------------------
    log_box = tk.Text(root, height=14, wrap="word")
    log_box.pack(fill="both", expand=True, **pad)
    run_btn = ttk.Button(root, text="Phân tích & tạo timeline")
    run_btn.pack(pady=6)
    messages: "queue.Queue" = queue.Queue()

    def log(msg: str):
        messages.put(("log", msg))

    def collect() -> JobSettings:
        def f(var, default=None):
            text = var.get().strip()
            return float(text) if text else default

        j = JobSettings()
        j.cameras = list(cam_list.get(0, "end"))
        j.audio = audio_var.get().strip() or None
        j.broll_dir = broll_var.get().strip() or None
        j.srt = srt_var.get().strip() or None
        j.timeline_name = name_var.get().strip() or "AutoEdit"
        j.silence.threshold_db = f(thr_var, -35.0)
        j.silence.min_silence = f(mins_var, 0.5)
        j.silence.padding = f(padd_var, 0.12)
        j.multicam.mode = MODES[mode_var.get()]
        wide_no = f(wide_var)
        j.multicam.wide_camera = int(wide_no) - 1 if wide_no else None
        j.multicam.min_shot = f(minshot_var, 2.0)
        j.multicam.max_shot = f(maxshot_var, 8.0)
        j.multicam.sync = "audio" if sync_var.get() else "none"
        j.broll.enabled = br_on.get()
        j.broll.fill = fill_var.get()
        j.broll.interval = f(int_var, 12.0)
        j.broll.duration = f(dur_var, 3.0)
        return j

    def worker(j: JobSettings, fps: Optional[float]):
        try:
            plan = analyze(j, fps, log)
            log(describe(plan))
            messages.put(("plan", (j, plan)))
        except Exception as exc:
            log(traceback.format_exc())
            messages.put(("error", str(exc)))

    builder_holder = {}

    def start():
        try:
            j = collect()
        except ValueError:
            messagebox.showerror("AutoEdit", "Giá trị số không hợp lệ.")
            return
        if not j.cameras:
            messagebox.showerror("AutoEdit", "Hãy thêm ít nhất một file camera.")
            return
        try:
            j.save(SETTINGS_FILE)
        except OSError:
            pass
        log_box.delete("1.0", "end")
        try:
            from . import ffmpeg_tools as ff
            from .resolve_bridge import ResolveBuilder, get_resolve
            builder = ResolveBuilder(get_resolve(resolve_hint), log)
            fps = builder.timeline_fps(ff.probe(j.cameras[0]).fps)
            builder_holder["b"] = builder
        except Exception as exc:
            messagebox.showerror("AutoEdit", str(exc))
            return
        run_btn.configure(state="disabled")
        threading.Thread(target=worker, args=(j, fps), daemon=True).start()

    def poll():
        try:
            while True:
                kind, payload = messages.get_nowait()
                if kind == "log":
                    log_box.insert("end", payload + "\n")
                    log_box.see("end")
                elif kind == "plan":
                    j, plan = payload
                    try:  # Resolve calls stay on the UI thread
                        builder_holder["b"].build(plan, j.timeline_name)
                        log_box.insert("end", "Xong! Mở trang Edit trong Resolve để xem.\n")
                    except Exception as exc:
                        log_box.insert("end", traceback.format_exc())
                        messagebox.showerror("AutoEdit", str(exc))
                    run_btn.configure(state="normal")
                elif kind == "error":
                    messagebox.showerror("AutoEdit", payload)
                    run_btn.configure(state="normal")
        except queue.Empty:
            pass
        root.after(150, poll)

    run_btn.configure(command=start)
    poll()
    root.mainloop()


if __name__ == "__main__":
    main()
