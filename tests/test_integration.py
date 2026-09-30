"""End-to-end: synthetic multi-clip, multi-camera event -> plan -> fake Resolve.

One 60 s "event" soundtrack is recorded by:
  Cam 1 (DJI-style names):   0-25 s and 30-60 s
  Cam 2 (Canon-style names): 5-40 s and 45-58 s, clock 37 s fast,
                             clock read from creation_time metadata
There is silence at 12-14 s and 50-52 s.
"""

import datetime as dt
import os
import shutil
import subprocess

import pytest

from autoedit.config import JobSettings
from autoedit.pipeline import analyze
from autoedit.resolve_bridge import ResolveBuilder

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")

T0 = dt.datetime(2026, 9, 11, 14, 28, 0)
# loud/quiet pattern (never silent) plus two real silences
GATE = ("(0.35+0.65*gt(sin(2*PI*t*0.71)*sin(2*PI*t*0.23+1)+0.2*sin(2*PI*t*1.9),0))"
        "*(1-between(t,12,14))*(1-between(t,50,52))")
LEVEL = "(0.4+0.6*abs(sin(t*1.3)))"


def run(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def make_clip(event_wav, path, start, dur, color, creation=None):
    meta = ["-metadata", f"creation_time={creation}"] if creation else []
    run("-f", "lavfi", "-i", f"color=c={color}:s=160x90:r=25:d={dur}",
        "-ss", str(start), "-t", str(dur), "-i", str(event_wav),
        "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", "-shortest", *meta, str(path))


@pytest.fixture(scope="module")
def event(tmp_path_factory):
    d = tmp_path_factory.mktemp("event")
    wav = d / "event.wav"
    run("-f", "lavfi", "-i", "anoisesrc=d=60:c=pink:a=0.5:r=48000:s=42",
        "-af", f"volume='{LEVEL}*{GATE}':eval=frame", str(wav))
    cam1, cam2 = d / "Cam 1", d / "Cam 2"
    cam1.mkdir()
    cam2.mkdir()
    for i, (start, dur) in enumerate([(0, 25), (30, 30)], 1):
        stamp = (T0 + dt.timedelta(seconds=start)).strftime("%Y%m%d%H%M%S")
        make_clip(wav, cam1 / f"V1-000{i}_DJI_{stamp}_000{i}_D.mp4", start, dur, "blue")
    for i, (start, dur) in enumerate([(5, 35), (45, 13)], 1):
        clock = T0 + dt.timedelta(seconds=start + 37)
        make_clip(wav, cam2 / f"MVI_590{i}.MP4", start, dur, "red",
                  clock.strftime("%Y-%m-%dT%H:%M:%S.000000Z"))
    broll_dir = d / "broll"
    broll_dir.mkdir()
    make_clip(wav, broll_dir / "bien.mp4", 0, 6, "green")
    return cam1, cam2, broll_dir


def job_for(event, **multicam):
    cam1, cam2, broll_dir = event
    job = JobSettings(cameras=[str(cam1), str(cam2)], broll_dir=str(broll_dir))
    for k, v in multicam.items():
        setattr(job.multicam, k, v)
    return job


def test_event_is_synced_cut_and_laid_out_per_camera(event):
    logs = []
    plan = analyze(job_for(event), 25.0, logs.append)
    text = "\n".join(logs)
    assert "khớp 2/2 clip" in text, text
    assert "+37" in text, text  # detected Cam 2 clock offset

    # Cam 2's first clip starts 5 s after Cam 1's first clip.
    cam2_audio = sorted((e for e in plan.by_kind("audio") if e.track == 2),
                        key=lambda e: e.record_frame)
    first = cam2_audio[0]
    # it begins at axis 5 s; before the 12-14 s cut, record == axis
    assert abs(first.record_frame / 25 - 5.0) < 0.06
    assert first.source_start == pytest.approx(0.0, abs=0.06)

    # 60 s recorded, 2 silences of 2 s (minus padding) removed.
    assert 55.5 < plan.total_frames / 25 < 57.0
    for e in plan.events:
        if e.kind in ("camera", "audio"):
            assert os.path.basename(os.path.dirname(e.path)) == f"Cam {e.track}"
    assert {e.track for e in plan.by_kind("broll")} == {3}

    # At every moment the chosen camera's video is enabled and above it all is off.
    for rec, frames, cam in plan.shots:
        mid = rec + frames // 2
        live = [e for e in plan.by_kind("camera")
                if e.record_frame <= mid < e.record_frame + e.duration]
        on = [e.camera for e in live if e.enabled]
        assert max(on) == cam, (rec, cam, [(e.camera, e.enabled) for e in live])


def test_without_switching_everything_is_stacked_and_enabled(event):
    plan = analyze(job_for(event, mode="off"), 25.0, lambda m: None)
    assert all(e.enabled for e in plan.events)
    assert {e.track for e in plan.by_kind("camera")} == {1, 2}


# ---------------------------------------------------------------- fake Resolve
class FakeItem:
    def __init__(self, path, fps=25):
        self.path, self.fps = path, fps

    def GetClipProperty(self, key):
        return {"File Path": self.path, "FPS": str(self.fps)}[key]


class FakeTimelineItem:
    def __init__(self, info, inclusive):
        self.info = info
        self.enabled = True
        self.dur = info["endFrame"] - info["startFrame"] + (1 if inclusive else 0)

    def GetDuration(self): return self.dur
    def GetStart(self): return self.info["recordFrame"]
    def SetClipEnabled(self, value):
        self.enabled = value
        return True


class FakeTimeline:
    def __init__(self, name):
        self.name, self.items = name, []
        self.tracks = {"video": 1, "audio": 1}

    def GetName(self): return self.name
    def GetStartFrame(self): return 90000
    def GetTrackCount(self, kind): return self.tracks[kind]
    def AddTrack(self, kind, sub=None):
        self.tracks[kind] += 1
        return True
    def GetItemListInTrack(self, kind, index):
        want = 1 if kind == "video" else 2
        return [i for i in self.items
                if i.info["trackIndex"] == index and i.info["mediaType"] == want]
    def DeleteClips(self, items, ripple):
        for i in items:
            self.items.remove(i)
        return True


class FakeFolder:
    def __init__(self, name):
        self.name, self.clips, self.subs = name, [], []
    def GetName(self): return self.name
    def GetClipList(self): return self.clips
    def GetSubFolderList(self): return self.subs


class FakeMediaPool:
    def __init__(self, project, inclusive):
        self.project, self.inclusive = project, inclusive
        self.root = FakeFolder("Master")
        self.current = self.root

    def GetRootFolder(self): return self.root
    def AddSubFolder(self, parent, name):
        f = FakeFolder(name)
        parent.subs.append(f)
        return f
    def SetCurrentFolder(self, f):
        self.current = f
        return True
    def ImportMedia(self, paths):
        items = [FakeItem(p) for p in reversed(paths)]  # order not guaranteed
        self.current.clips.extend(items)
        return items
    def CreateEmptyTimeline(self, name):
        tl = FakeTimeline(name)
        self.project.timelines.append(tl)
        return tl
    def AppendToTimeline(self, infos):
        out = [FakeTimelineItem(i, self.inclusive) for i in infos]
        self.project.current.items.extend(out)
        return out


class FakeProject:
    def __init__(self, inclusive):
        self.timelines, self.current = [], None
        self.pool = FakeMediaPool(self, inclusive)
        self.settings = {"timelineFrameRate": "24"}
    def GetMediaPool(self): return self.pool
    def GetTimelineCount(self): return len(self.timelines)
    def GetTimelineByIndex(self, i): return self.timelines[i - 1]
    def SetCurrentTimeline(self, tl):
        self.current = tl
        return True
    def GetSetting(self, k): return self.settings[k]
    def SetSetting(self, k, v):
        self.settings[k] = v
        return True


class FakeResolve:
    def __init__(self, inclusive):
        self.project = FakeProject(inclusive)
    def GetProjectManager(self): return self
    def GetCurrentProject(self): return self.project


@pytest.mark.parametrize("inclusive", [True, False])
def test_builder_creates_tracks_and_disables_unchosen_angles(event, inclusive):
    fake = FakeResolve(inclusive)
    builder = ResolveBuilder(fake, log=lambda m: None)
    assert builder.timeline_fps(25.0) == 25.0  # empty project adopts footage fps

    plan = analyze(job_for(event), 25.0, lambda m: None)
    tl = builder.build(plan, "AutoEdit")
    builder.build(plan, "AutoEdit")
    assert [t.GetName() for t in fake.project.timelines] == ["AutoEdit", "AutoEdit 2"]
    assert builder.end_inclusive is inclusive
    assert tl.tracks == {"video": 3, "audio": 2}

    for track in (1, 2):
        audio = sorted(tl.GetItemListInTrack("audio", track), key=lambda i: i.GetStart())
        video = tl.GetItemListInTrack("video", track)
        assert audio and video
        assert {i.info["mediaPoolItem"].path for i in audio} == \
            {i.info["mediaPoolItem"].path for i in video}
    v1 = tl.GetItemListInTrack("video", 1)
    assert all(i.enabled for i in v1)
    disabled = [i for i in tl.GetItemListInTrack("video", 2) if not i.enabled]
    assert len(disabled) == len([e for e in plan.events if not e.enabled]) > 0
    assert len(fake.project.pool.root.subs[0].clips) == len({e.path for e in plan.events})
