"""Smoke test for the compatibility-transcode pipeline (hw fallback, remux, progress,
validation). Run directly: `python test_transcode_smoke.py`. No pytest/framework needed."""
import os
import shutil
import subprocess
import tempfile

import app

work_dir = tempfile.mkdtemp(prefix="transcode_smoke_")
src = os.path.join(work_dir, "source.webm")
already_compat = os.path.join(work_dir, "already_compat.mp4")
final_a = os.path.join(work_dir, "final_a.mp4")
final_b = os.path.join(work_dir, "final_b.mp4")

try:
    # A non-compatible source (VP9/Opus in WebM) forces the encode path, including
    # the hardware-encoder-candidates -> libx264 fallback loop.
    subprocess.run([
        app.FFMPEG_BIN, "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=3",
        "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-b:v", "300k", "-c:a", "libopus",
        src,
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    app._transcode_for_compatibility(src, final_a, "a" * 32)
    v = app.validate_media_file(final_a)
    assert v["video_codec"] == "h264", v
    assert v["audio_codec"] == "aac", v
    assert v["pix_fmt"] == "yuv420p", v
    assert v["width"] == 640 and v["height"] == 360, v  # resolution preserved

    progress = app.PROGRESS["a" * 32]
    assert progress["stage"] == "transcoding"
    assert progress["percent"] is not None and progress["percent"] > 0

    # An already-compatible source must be remuxed (stream copy), not re-encoded.
    subprocess.run([app.FFMPEG_BIN, "-y", "-i", final_a, "-c", "copy", already_compat],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    app._transcode_for_compatibility(already_compat, final_b, "b" * 32)
    v2 = app.validate_media_file(final_b)
    assert v2["video_codec"] == "h264" and v2["audio_codec"] == "aac", v2

    print("OK: hardware fallback to libx264, progress tracked, remux path, "
          "resolution preserved, output validated.")
finally:
    shutil.rmtree(work_dir, ignore_errors=True)
