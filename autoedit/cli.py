"""Command line interface.

    python -m autoedit -c "D:/Show/Cam 1" -c "D:/Show/Cam 2" --broll-dir broll/
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .config import JobSettings
from .pipeline import analyze
from .planner import describe


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="autoedit",
        description="Tự động dựng video trong DaVinci Resolve: cắt khoảng lặng, "
                    "đảo góc máy, chèn B-roll.")
    p.add_argument("-c", "--camera", action="append", default=[],
                   help="thư mục (hoặc file) của một camera; lặp lại cho Cam 2, Cam 3... "
                        "Cam 1 là chuẩn để đồng bộ")
    p.add_argument("--config", help="đọc cài đặt từ file JSON")
    p.add_argument("--save-config", help="lưu cài đặt ra file JSON")
    p.add_argument("--broll-dir", help="thư mục chứa clip B-roll")
    p.add_argument("--srt", help="phụ đề .srt (tính từ đầu clip đầu tiên của Cam 1) "
                                 "để khớp B-roll theo từ khoá")
    p.add_argument("--name", dest="timeline_name", help="tên timeline")

    g = p.add_argument_group("cắt khoảng lặng")
    g.add_argument("--no-silence-cut", action="store_true",
                   help="không cắt khoảng lặng (chỉ bỏ đoạn không camera nào quay)")
    g.add_argument("--threshold", type=float, help="ngưỡng im lặng (dB), vd -35")
    g.add_argument("--min-silence", type=float, help="khoảng lặng tối thiểu để cắt (s)")
    g.add_argument("--padding", type=float, help="giữ lại trước/sau lời nói (s)")

    g = p.add_argument_group("đảo góc máy")
    g.add_argument("--mode", choices=["rhythm", "speaker", "off"],
                   help="rhythm: đảo theo nhịp; speaker: theo người đang nói")
    g.add_argument("--wide-cam", type=int, help="số thứ tự camera toàn cảnh (1, 2, ...)")
    g.add_argument("--min-shot", type=float)
    g.add_argument("--max-shot", type=float)
    g.add_argument("--no-sync", action="store_true",
                   help="không đồng bộ theo sóng âm, chỉ xếp theo giờ quay")
    g.add_argument("--sync-window", type=float,
                   help="tìm khớp âm thanh trong +- bấy nhiêu giây quanh giờ quay")

    g = p.add_argument_group("B-roll")
    g.add_argument("--no-broll", action="store_true")
    g.add_argument("--broll-interval", type=float)
    g.add_argument("--broll-duration", type=float)
    g.add_argument("--keyword-only", action="store_true",
                   help="chỉ chèn B-roll khi khớp từ khóa trong phụ đề")

    p.add_argument("--dry-run", action="store_true",
                   help="chỉ phân tích và in kế hoạch dựng, không cần mở Resolve")
    p.add_argument("--fps", type=float, help="frame rate khi --dry-run")
    p.add_argument("--plan-out", help="ghi kế hoạch dựng ra file JSON")
    return p


def job_from_args(args: argparse.Namespace) -> JobSettings:
    job = JobSettings.load(args.config) if args.config else JobSettings()
    if args.camera:
        job.cameras = args.camera
    for attr in ("broll_dir", "srt", "timeline_name"):
        if getattr(args, attr):
            setattr(job, attr, getattr(args, attr))
    s, m, b = job.silence, job.multicam, job.broll
    if args.no_silence_cut: s.enabled = False
    if args.threshold is not None: s.threshold_db = args.threshold
    if args.min_silence is not None: s.min_silence = args.min_silence
    if args.padding is not None: s.padding = args.padding
    if args.mode: m.mode = args.mode
    if args.wide_cam is not None: m.wide_camera = args.wide_cam - 1
    if args.min_shot is not None: m.min_shot = args.min_shot
    if args.max_shot is not None: m.max_shot = args.max_shot
    if args.no_sync: m.sync = "none"
    if args.sync_window is not None: m.sync_window = args.sync_window
    if args.no_broll: b.enabled = False
    if args.broll_interval is not None: b.interval = args.broll_interval
    if args.broll_duration is not None: b.duration = args.broll_duration
    if args.keyword_only: b.fill = False
    return job


def main(argv: Optional[List[str]] = None, resolve_hint: Optional[dict] = None) -> int:
    args = build_parser().parse_args(argv)
    job = job_from_args(args)
    if args.save_config:
        job.save(args.save_config)
    if not job.cameras:
        print("Cần ít nhất một --camera (hoặc --config).", file=sys.stderr)
        return 2

    builder = None
    fps = args.fps
    if not args.dry_run:
        from . import ffmpeg_tools as ff
        from .resolve_bridge import ResolveBuilder, get_resolve
        builder = ResolveBuilder(get_resolve(resolve_hint))
        from .sources import collect_files
        first = collect_files(job.cameras[0])
        if not first:
            print(f"Cam 1: không có file video trong {job.cameras[0]}", file=sys.stderr)
            return 2
        fps = builder.timeline_fps(ff.probe(first[0]).fps)

    plan = analyze(job, fps)
    print(describe(plan))
    if args.plan_out:
        with open(args.plan_out, "w", encoding="utf-8") as f:
            json.dump(plan.to_dict(), f, ensure_ascii=False, indent=2)
    if builder:
        builder.build(plan, job.timeline_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
