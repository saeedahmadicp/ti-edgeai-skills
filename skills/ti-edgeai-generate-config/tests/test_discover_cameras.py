"""discover_cameras.sh lists capture nodes and skips codec nodes (v4l2-ctl and /dev/video* are simulated)."""
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "discover_cameras.sh"
FAKE_V4L2 = r'''#!/bin/bash
dev=""; mode=""
while [ $# -gt 0 ]; do case "$1" in -d) dev=$2; shift;; --all) mode=all;; --list-formats-ext) mode=fmt;; esac; shift; done
case "$dev:$mode" in
  *video0:all) printf "Driver Info:\n\tCard type : vxd-dec\nDevice Caps : Video Memory-to-Memory Multiplanar\n";;
  *video2:all) printf "Driver Info:\n\tCard type      : Fake Webcam\n\tDevice Caps : Video Capture, Streaming\n";;
  *video2:fmt) printf "\t[0]: YUYV (YUYV 4:2:2)\n\t\tSize: Discrete 640x360\n\t\t\tInterval: Discrete 0.033s (30.000 fps)\n";;
  *) exit 1;;
esac
'''


class Discover(unittest.TestCase):
    def run_script(self, devices):
        root = Path(tempfile.mkdtemp())
        (root / "bin").mkdir()
        v = root / "bin" / "v4l2-ctl"
        v.write_text(FAKE_V4L2)
        v.chmod(v.stat().st_mode | stat.S_IEXEC)
        # the script globs /dev/video*; run it with a rewritten glob so no real device is needed
        text = SCRIPT.read_text().replace("/dev/video*", f"{root}/video*")
        script = root / "s.sh"
        script.write_text(text)
        for d in devices:
            (root / d).write_text("")
        env = dict(os.environ, PATH=f"{root / 'bin'}:{os.environ['PATH']}")
        env.pop("BOARD", None)
        return subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)

    def test_lists_camera_and_skips_codec(self):
        r = self.run_script(["video0", "video2"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Fake Webcam", r.stdout)
        self.assertIn("640x360", r.stdout)
        self.assertNotIn("vxd-dec", r.stdout)

    def test_reports_when_nothing_found(self):
        r = self.run_script(["video0"])
        self.assertIn("no V4L2 capture device found", r.stdout)


if __name__ == "__main__":
    unittest.main()
