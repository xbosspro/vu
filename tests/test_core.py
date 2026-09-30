import random

import pytest

from autoedit import broll, ffmpeg_tools as ff
from autoedit.config import BrollSettings, JobSettings, MulticamSettings
from autoedit.multicam import Shot, envelope_loudness, plan_shots
from autoedit.planner import build_plan
from autoedit.silence import (TimeMap, intersect, keep_intervals,
                              silences_from_envelope, union)
from autoedit.sources import (SourceClip, collect_files, creation_seconds,
                              estimate_starts, filename_time, timecode_seconds)
from autoedit.sync import Axis, WINDOW, best_lag, locate, normalize, search


# ------------------------------------------------------------------ ffmpeg
def test_parse_rms_log_handles_inf():
    log = ("lavfi.astats.Overall.RMS_level=-inf\n"
           "lavfi.astats.Overall.RMS_level=-20.5\n")
    assert ff.parse_rms_log(log) == [ff.FLOOR_DB, -20.5]


def test_parse_probe_reads_fps_and_clock_tags():
    info = ff.parse_probe("x", {
        "streams": [{"codec_type": "video", "avg_frame_rate": "30000/1001",
                     "tags": {"timecode": "14:28:44:12"}},
                    {"codec_type": "audio"}],
        "format": {"duration": "12.5", "tags": {"creation_time": "2026-09-11T07:28:44.000000Z"}}})
    assert info.fps == pytest.approx(29.97, abs=0.01)
    assert info.duration == 12.5 and info.has_audio and info.has_video
    assert info.creation_time.startswith("2026-09-11") and info.timecode == "14:28:44:12"


# ------------------------------------------------------------------ sources
def test_filename_time_dji_and_phone():
    a = filename_time("V1-0001_DJI_20260911142844_0001_D.mp4")
    b = filename_time("VID_20260911_142914.mp4")
    assert a is not None and b - a == 30
    assert filename_time("MVI_5903.MP4") is None


def test_creation_and_timecode_parsing():
    assert creation_seconds("2026-09-11T07:28:44.500000Z") % 60 == pytest.approx(44.5)
    assert creation_seconds("1970-01-01T00:00:00Z") is None
    assert timecode_seconds("01:00:02:12", 25) == pytest.approx(3602.48)


def test_estimate_starts_prefers_names_and_detects_end_stamps():
    clips = [SourceClip(f"DJI_20260911142800_000{i}.mp4", 20) for i in (1,)] + \
            [SourceClip("DJI_20260911142830_0002.mp4", 20)]
    method, starts = estimate_starts(clips)
    assert method == "tên file" and starts[1] - starts[0] == 30

    # creation_time stamped at the END of each recording: 0-20 and 25-45 s
    end_stamped = [SourceClip("a.mp4", 20, creation_time="2026-01-01T00:00:20Z"),
                   SourceClip("b.mp4", 20, creation_time="2026-01-01T00:00:45Z")]
    method, starts = estimate_starts(end_stamped)
    assert "kết thúc" not in method  # no overlap either way -> keep start reading
    # read as starts, b (30-35) would sit inside a (20-40); read as ends: 0-20, 25-30
    overlapping = [SourceClip("a.mp4", 20, creation_time="2026-01-01T00:00:20Z"),
                   SourceClip("b.mp4", 5, creation_time="2026-01-01T00:00:30Z")]
    method, starts = estimate_starts(overlapping)
    assert "kết thúc" in method and starts[1] - starts[0] == 25

    assert estimate_starts([SourceClip("MVI_1.MP4", 5)]) == ("thứ tự file", None)


def test_collect_files_recursive_natural_order(tmp_path):
    (tmp_path / "Proxy").mkdir()
    (tmp_path / "Proxy" / "x.mp4").write_bytes(b"")
    (tmp_path / "sub").mkdir()
    for name in ["clip10.mp4", "clip2.MOV", "notes.txt", "._clip3.mp4"]:
        (tmp_path / name).write_bytes(b"")
    (tmp_path / "sub" / "clip1.mp4").write_bytes(b"")
    names = [p.replace(str(tmp_path), "").lstrip("/\\") for p in collect_files(str(tmp_path))]
    assert names == ["clip2.MOV", "clip10.mp4", "sub/clip1.mp4"] or \
        names == ["clip2.MOV", "clip10.mp4", "sub\\clip1.mp4"]


# ------------------------------------------------------------------ silence
def test_keep_intervals_pads_merges_and_drops():
    silences = [(0.0, 1.0), (3.0, 3.1), (5.0, 8.0), (8.2, 10.0)]
    assert keep_intervals(silences, 10.0, padding=0.1, min_keep=0.5) == [(0.9, 5.1)]


def test_silences_from_envelope():
    env = [-20] * 10 + [-60] * 12 + [-20] * 5 + [-60] * 3
    assert silences_from_envelope(env, 0.05, -35, 0.5) == [(0.5, pytest.approx(1.1))]


def test_union_and_intersect():
    assert union([(5, 8), (0, 2), (1, 3)]) == [(0, 3), (5, 8)]
    assert intersect([(0, 4), (6, 10)], [(1, 7)]) == [(1, 4), (6, 7)]


def test_time_map():
    tm = TimeMap([(1.0, 3.0), (5.0, 6.0)])
    assert tm.to_output(2.0) == 1.0 and tm.to_output(4.0) == 2.0
    assert tm.to_output(4.0, snap_forward=False) is None


# ------------------------------------------------------------------ multicam
def test_rhythm_switches_on_jump_cut_and_max_shot():
    ms = MulticamSettings(mode="rhythm", min_shot=2, max_shot=4)
    shots = plan_shots([(0, 3), (4, 14)], 2, ms)
    cams = [(s.start, s.end, s.camera) for s in shots]
    assert cams[0] == (0, 3, 0)
    assert cams[1] == (4, 8, 1)
    assert cams[2][2] == 0 and cams[2][0] == 8


def test_shots_only_use_cameras_with_footage():
    ms = MulticamSettings(mode="rhythm", min_shot=1, max_shot=2)
    coverage = [[(0, 5)], [(3, 10)]]  # cam1 stops at 5, cam2 starts at 3
    shots = plan_shots([(0, 10)], 2, ms, coverage=coverage)
    for sh in shots:
        a, b = coverage[sh.camera][0]
        assert a <= sh.start and sh.end <= b
    assert shots[-1].camera == 1


def test_speaker_mode_follows_loud_mic():
    def loud(cam, t0, t1):
        return -20.0 if (cam == 0) == (t0 < 5) else -50.0

    ms = MulticamSettings(mode="speaker", min_shot=1.5, max_shot=100)
    shots = plan_shots([(0, 10)], 2, ms, loud)
    assert shots[0].camera == 0
    switch = [s for s in shots if s.camera == 1][0]
    assert 4.0 <= switch.start <= 5.0


def test_speaker_mode_goes_wide_when_both_talk():
    ms = MulticamSettings(mode="speaker", wide_camera=2, min_shot=1, max_shot=3)
    shots = plan_shots([(0, 10)], 3, ms, lambda c, a, b: -20.0)
    assert all(s.camera == 2 for s in shots)


def test_envelope_loudness():
    lf = envelope_loudness([[-60.0] * 10 + [-10.0] * 10], 0.1)
    assert lf(0, 1.0, 1.5) == pytest.approx(-10.0)
    assert lf(0, 0.0, 0.5) == pytest.approx(-60.0)


# ------------------------------------------------------------------ sync
def test_best_lag_recovers_shift():
    random.seed(1)
    ref = [random.uniform(-60, -10) for _ in range(400)]
    other = [-60.0] * 25 + ref
    assert best_lag(normalize(ref), normalize(other), range(-50, 51), 100) == 25


@pytest.mark.parametrize("use_numpy", [False, True])
def test_search_finds_clip_on_axis(monkeypatch, use_numpy):
    import autoedit.sync as sync
    if use_numpy and sync._np is None:
        pytest.skip("numpy not installed")
    if not use_numpy:
        monkeypatch.setattr(sync, "_np", None)
    random.seed(2)
    axis = normalize([random.uniform(-60, -10) for _ in range(500)])
    clip = axis[120:220]
    assert search(axis, clip, -99, 499)[0] == 120
    # clip hanging off the start of the axis still matches its overlap
    idx, score = search(axis, [0.5] * 20 + axis[:80], -99, 499)
    assert idx == -20


def test_locate_whole_axis_and_near_guess():
    random.seed(3)
    env = [random.choice([-70, -40, -25, -15]) for _ in range(2400)]  # 120 s @ 50 ms
    ref = SourceClip("ref.mp4", 120.0, envelope=env)
    axis = Axis([ref])
    other = SourceClip("other.mp4", 30.0, envelope=env[800:1400])  # starts at 40 s
    pos, score = locate(axis, other, None, 0)
    assert pos == pytest.approx(40.0, abs=WINDOW) and score > 0.8
    pos, _ = locate(axis, other, 45.0, 10.0)
    assert pos == pytest.approx(40.0, abs=WINDOW)
    pos, _ = locate(axis, other, 90.0, 5.0)  # wrong guess, narrow window
    assert pos is None


# ------------------------------------------------------------------ broll
def test_broll_keyword_matching_vietnamese():
    clip = broll.BrollClip("/x/ca-phe+Sài_Gòn_02.mp4", 10.0,
                           broll.phrases_from_filename("/x/ca-phe+Sài_Gòn_02.mp4"))
    assert clip.phrases == [["ca", "phe"], ["sai", "gon"]]
    assert broll.match_phrase(clip, "Buổi sáng ở Sài Gòn") == "sai gon"
    assert broll.match_phrase(clip, "uống cà phê") == "ca phe"
    assert broll.match_phrase(clip, "cá hồi") is None


def test_parse_srt():
    text = "1\n00:00:01,000 --> 00:00:02,500\nXin chào\n\n2\n00:00:03,000 --> 00:00:04,000\nmột\nhai\n"
    cues = broll.parse_srt(text)
    assert [(c.start, c.end, c.text) for c in cues] == [(1.0, 2.5, "Xin chào"),
                                                        (3.0, 4.0, "một hai")]


def test_plan_broll_keyword_then_fill_without_overlap():
    a = broll.BrollClip("a.mp4", 10, [["bien"]])
    b = broll.BrollClip("b.mp4", 10, [["nui"]])
    s = BrollSettings(interval=10, duration=3, first_after=5, tail=2, min_gap=2)
    placed = broll.plan_broll(60.0, [a, b], s, [broll.Cue(20.0, 22.0, "đi biển")])
    kw = [p for p in placed if p.reason.startswith("keyword")]
    assert kw and kw[0].start == 20.0 and kw[0].clip is a
    for p, q in zip(placed, placed[1:]):
        assert p.start + p.duration + s.min_gap <= q.start
    assert placed[0].source_start == pytest.approx(3.5)


# ------------------------------------------------------------------ planner
def test_plan_puts_each_camera_on_its_own_tracks_and_disables_unchosen():
    fps = 25.0
    cam1 = [SourceClip("c1a.mp4", 6.0, position=0.0), SourceClip("c1b.mp4", 4.0, position=8.0)]
    cam2 = [SourceClip("c2.mp4", 10.0, position=1.0)]
    intervals = [(0.0, 5.0), (6.0, 11.0)]
    shots = [Shot(0.0, 2.0, 0, 0), Shot(2.0, 5.0, 1, 0), Shot(6.0, 8.0, 1, 1),
             Shot(8.0, 11.0, 0, 1)]
    plan = build_plan(fps, intervals, shots, [cam1, cam2])
    assert plan.total_frames == 250

    for e in plan.events:
        assert e.track == e.camera + 1
    v2 = sorted((e for e in plan.by_kind("camera") if e.track == 2), key=lambda e: e.record_frame)
    # Cam 2 exists from axis 1 s; enabled only while it is the chosen angle.
    assert [(e.record_frame, e.duration, e.enabled) for e in v2] == [
        (25, 25, False), (50, 75, True), (125, 50, True), (175, 75, False)]
    assert v2[0].source_start == pytest.approx(0.0)
    v1 = [e for e in plan.by_kind("camera") if e.track == 1]
    assert all(e.enabled for e in v1)  # lowest layer always on
    # audio of each camera is continuous where it recorded
    a1 = sum(e.duration for e in plan.by_kind("audio") if e.track == 1)
    assert a1 == 125 + 75  # c1a covers axis 0-5, c1b covers axis 8-11


def test_plan_without_switching_keeps_everything_enabled():
    cams = [[SourceClip("a.mp4", 5.0)], [SourceClip("b.mp4", 5.0)]]
    plan = build_plan(25, [(0.0, 5.0)], [Shot(0, 5, 0, 0)], cams, switching=False)
    assert all(e.enabled for e in plan.events)


def test_job_settings_ignore_unknown_keys():
    job = JobSettings.from_dict({"cameras": ["a"], "audio": "old", "silence": {"x": 1}})
    assert job.cameras == ["a"] and job.silence.enabled
