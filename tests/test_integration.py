"""End-to-end: synthetic footage through ffmpeg, then a fake Resolve API."""

import os
import shutil
import subprocess

import pytest

from autoedit.config import JobSettings
from autoedit.pipeline import analyze
from autoedit.resolve_bridge import ResolveBuilder

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")

# speech-like bursts separated by silences (enable expressions in seconds)
SPEECH = "between(t,1,4)+between(t,6,9)+between(t,12,17)+between(t,19,20.5)"


def make_clip(path, lead_in=0.0, duration=22.0, color="blue"):
    """Test pattern video; audio bursts delayed by `lead_in` seconds."""
    total = duration + lead_in
    expr = SPEECH.replace("t,", f"t-{lead_in},") if lead_in else SPEECH
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c={color}:s=160x90:r=25:d={total}",
        "-f", "lavfi", "-i", f"anoisesrc=d={total}:c=pink:a=0.3:r=16000",
        "-filter_complex", f"[1:a]volume='if({expr},1,0)':eval=frame[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", "-shortest", str(path),
    ], check=True)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    cam1, cam2 = d / "cam1.mp4", d / "cam2.mp4"
    make_clip(cam1)
    make_clip(cam2, lead_in=1.5, color="red")
    broll_dir = d / "broll"
    broll_dir.mkdir()
    make_clip(broll_dir / "bien.mp4", duration=6, color="green")
    make_clip(broll_dir / "nui-rung.mp4", duration=6, color="yellow")
    srt = d / "talk.srt"
    srt.write_text("1\n00:00:12,500 --> 00:00:14,000\nhôm nay đi biển\n", encoding="utf-8")
    return cam1, cam2, broll_dir, srt


def test_pipeline_cuts_syncs_and_places_broll(media):
    cam1, cam2, broll_dir, srt = media
    job = JobSettings(cameras=[str(cam1), str(cam2)], broll_dir=str(broll_dir),
                      srt=str(srt))
    job.multicam.mode = "rhythm"
    job.multicam.sync_analyze = 20
    job.multicam.sync_max_offset = 5
    job.broll.interval = 6
    job.broll.min_gap = 1
    logs = []
    plan = analyze(job, 25.0, logs.append)

    # 4 speech bursts of 3+3+5+1.5 s plus padding, silences removed.
    assert 12.0 < plan.total_frames / 25.0 < 14.5
    cams = plan.by_kind("camera")
    assert {os.path.basename(e.path) for e in cams} == {"cam1.mp4", "cam2.mp4"}
    # camera 2 recorded 1.5 s earlier -> its source times are shifted by +1.5 s
    offs = [e for e in cams if e.path == str(cam2)]
    assert any("+1.5" in l for l in logs), logs
    assert sum(e.duration for e in cams) == plan.total_frames
    brolls = plan.by_kind("broll")
    assert any(os.path.basename(e.path) == "bien.mp4" for e in brolls)
    assert all(e.track == 2 for e in brolls)
    assert offs


# ---------------------------------------------------------------- fake Resolve
class FakeItem:
    def __init__(self, path, fps=25):
        self.path, self.fps = path, fps

    def GetClipProperty(self, key):
        return {"File Path": self.path, "FPS": str(self.fps)}[key]


class FakeTimelineItem:
    def __init__(self, info, inclusive):
        self.info = info
        self.dur = info["endFrame"] - info["startFrame"] + (1 if inclusive else 0)

    def GetDuration(self):
        return self.dur


class FakeTimeline:
    def __init__(self, name):
        self.name, self.items, self.video_tracks = name, [], 1

    def GetName(self): return self.name
    def GetStartFrame(self): return 90000
    def GetTrackCount(self, kind): return self.video_tracks
    def AddTrack(self, kind):
        self.video_tracks += 1
        return True
    def DeleteClips(self, items, ripple):
        for i in items:
            self.items.remove(i)
        return True


class FakeFolder:
    def __init__(self, name, clips=()):
        self.name, self.clips, self.subs = name, list(clips), []
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
        items = [FakeItem(p) for p in paths]
        self.current.clips.extend(items)
        return items
    def CreateEmptyTimeline(self, name):
        tl = FakeTimeline(name)
        self.project.timelines.append(tl)
        return tl
    def AppendToTimeline(self, infos):
        tl = self.project.current
        out = [FakeTimelineItem(i, self.inclusive) for i in infos]
        tl.items.extend(out)
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
    def GetProjectManager(self):
        return self
    def GetCurrentProject(self):
        return self.project


@pytest.mark.parametrize("inclusive", [True, False])
def test_builder_places_frame_exact_clips(media, inclusive):
    cam1, cam2, broll_dir, _ = media
    fake = FakeResolve(inclusive)
    builder = ResolveBuilder(fake, log=lambda m: None)
    assert builder.timeline_fps(25.0) == 25.0  # empty project adopts footage fps

    job = JobSettings(cameras=[str(cam1), str(cam2)], broll_dir=str(broll_dir))
    job.multicam.sync = "none"
    plan = analyze(job, 25.0, lambda m: None)
    tl = builder.build(plan, "AutoEdit")
    builder.build(plan, "AutoEdit")
    assert [t.GetName() for t in fake.project.timelines] == ["AutoEdit", "AutoEdit 2"]

    assert builder.end_inclusive is inclusive
    assert tl.video_tracks == 2
    video = [i for i in tl.items if i.info["trackIndex"] == 1 and i.info["mediaType"] == 1]
    assert sum(i.GetDuration() for i in video) == plan.total_frames
    pos = 90000
    for i in sorted(video, key=lambda i: i.info["recordFrame"]):
        assert i.info["recordFrame"] == pos
        pos += i.GetDuration()
    # media imported once into the AutoEdit bin, even after a second build
    assert len(fake.project.pool.root.subs[0].clips) == len({e.path for e in plan.events})
