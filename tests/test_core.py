import math

import pytest

from autoedit import broll, ffmpeg_tools as ff
from autoedit.config import BrollSettings, MulticamSettings
from autoedit.multicam import Shot, envelope_loudness, plan_shots
from autoedit.planner import build_plan
from autoedit.silence import TimeMap, keep_intervals
from autoedit.sync import best_lag, _normalize


def test_parse_silencedetect_with_open_end():
    log = """
[silencedetect @ 0x1] silence_start: 1.5
[silencedetect @ 0x1] silence_end: 2.75 | silence_duration: 1.25
[silencedetect @ 0x1] silence_start: 9
"""
    assert ff.parse_silencedetect(log, 10.0) == [(1.5, 2.75), (9.0, 10.0)]


def test_parse_rms_log_handles_inf():
    log = ("lavfi.astats.Overall.RMS_level=-inf\n"
           "lavfi.astats.Overall.RMS_level=-20.5\n")
    assert ff.parse_rms_log(log) == [ff.FLOOR_DB, -20.5]


def test_parse_probe_fraction_fps():
    info = ff.parse_probe("x", {"streams": [{"codec_type": "video",
                                             "avg_frame_rate": "30000/1001"},
                                            {"codec_type": "audio"}],
                                "format": {"duration": "12.5"}})
    assert info.fps == pytest.approx(29.97, abs=0.01)
    assert info.duration == 12.5 and info.has_audio and info.has_video


def test_keep_intervals_pads_merges_and_drops():
    silences = [(0.0, 1.0), (3.0, 3.1), (5.0, 8.0), (8.2, 10.0)]
    # speech: 1-3, 3.1-5, 8-8.2 (too short after padding? 0.2+0.2=0.4 >= 0.3 keep)
    got = keep_intervals(silences, 10.0, padding=0.1, min_keep=0.5)
    assert got == [(0.9, 5.1)]


def test_time_map():
    tm = TimeMap([(1.0, 3.0), (5.0, 6.0)])
    assert tm.duration == 3.0
    assert tm.to_output(2.0) == 1.0
    assert tm.to_output(4.0) == 2.0  # in a gap -> next segment
    assert tm.to_output(4.0, snap_forward=False) is None
    assert tm.to_output(7.0) is None


def test_single_camera_one_shot_per_interval():
    shots = plan_shots([(0, 2), (3, 5)], 1, MulticamSettings())
    assert [(s.start, s.end, s.camera) for s in shots] == [(0, 2, 0), (3, 5, 0)]


def test_rhythm_switches_on_jump_cut_and_max_shot():
    ms = MulticamSettings(mode="rhythm", min_shot=2, max_shot=4)
    shots = plan_shots([(0, 3), (4, 14)], 2, ms)
    cams = [(s.start, s.end, s.camera) for s in shots]
    assert cams[0] == (0, 3, 0)
    assert cams[1] == (4, 8, 1)       # switched at jump cut, held max_shot
    assert cams[2][2] == 0 and cams[2][0] == 8


def test_speaker_mode_follows_loud_mic():
    # cam0 speaks 0-5s, cam1 speaks 5-10s
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


def test_envelope_loudness_uses_offset():
    env0 = [-60.0] * 10 + [-10.0] * 10
    lf = envelope_loudness([env0, env0], [0.0, -1.0], 0.1)
    assert lf(0, 1.0, 1.5) == pytest.approx(-10.0)
    assert lf(1, 1.0, 1.5) == pytest.approx(-60.0)


def test_best_lag_recovers_shift():
    import random
    random.seed(1)
    ref = [random.uniform(-60, -10) for _ in range(400)]
    other = [-60.0] * 25 + ref  # other started 25 samples earlier
    lag = best_lag(_normalize(ref), _normalize(other), range(-50, 51), 100)
    assert lag == 25


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
    cues = [broll.Cue(20.0, 22.0, "đi biển")]
    placed = broll.plan_broll(60.0, [a, b], s, cues)
    kw = [p for p in placed if p.reason.startswith("keyword")]
    assert kw and kw[0].start == 20.0 and kw[0].clip is a
    ordered = sorted(placed, key=lambda p: p.start)
    for p, q in zip(ordered, ordered[1:]):
        assert p.start + p.duration + s.min_gap <= q.start
    assert all(5 <= p.start and p.start + p.duration <= 58 for p in placed)
    assert ordered[0].source_start == pytest.approx(3.5)  # centred in clip


def test_build_plan_frames_are_contiguous():
    fps = 25.0
    intervals = [(0.0, 2.0), (3.0, 5.52)]
    shots = [Shot(0.0, 1.0, 0, 0), Shot(1.0, 2.0, 1, 0), Shot(3.0, 5.52, 0, 1)]
    plan = build_plan(fps, intervals, shots, "a.wav", ["c0.mp4", "c1.mp4"],
                      [0.0, 0.5], [10.0, 10.0])
    cams = plan.by_kind("camera")
    audio = plan.by_kind("audio")
    assert plan.total_frames == 50 + 63
    assert sum(e.duration for e in cams) == plan.total_frames
    assert sum(e.duration for e in audio) == plan.total_frames
    pos = 0
    for e in sorted(cams, key=lambda e: e.record_frame):
        assert e.record_frame == pos
        pos += e.duration
    assert cams[1].source_start == pytest.approx(1.5)  # offset applied


def test_build_plan_falls_back_when_camera_missing_footage():
    shots = [Shot(0.0, 4.0, 1, 0)]
    plan = build_plan(25, [(0.0, 4.0)], shots, "a.wav", ["c0", "c1"],
                      [0.0, -2.0], [10.0, 10.0])
    assert plan.by_kind("camera")[0].path == "c0"
    assert plan.notes
