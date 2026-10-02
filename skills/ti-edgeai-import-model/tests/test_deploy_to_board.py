"""deploy_to_board.sh against a simulated board (stub ssh/scp working on a temp directory). No hardware is touched."""
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "deploy_to_board.sh"

SSH = '#!/bin/bash\nshift\nexec bash -c "$*"\n'
SCP = '''#!/bin/bash
args=(); for a in "$@"; do case "$a" in -*) ;; *) args+=("$a");; esac; done
src=${args[0]}; dst=${args[1]#*:}
cp -r "$src" "$dst"
'''
APP = ('#!/bin/bash\n[ -n "$FAKE_LOG" ] && echo "$FAKE_LOG"\n[ -n "$FAKE_WRITE" ] && echo frame > "$FAKE_WRITE"\n'
       '[ "${FAKE_NOLOG:-0}" = 1 ] || echo "${FAKE_OFFLOAD:-Offloaded Nodes - 3, Total Nodes - 3}"\nexit ${FAKE_RC:-0}\n')


def exe(path, text):
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class Deploy(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.bin = self.root / "bin"; self.bin.mkdir()
        exe(self.bin / "ssh", SSH); exe(self.bin / "scp", SCP)
        self.zoo = self.root / "zoo"; self.zoo.mkdir()
        apps = self.root / "gst" / "apps_python"; apps.mkdir(parents=True)
        (self.root / "gst" / "configs").mkdir()
        exe(apps / "app_edgeai.py", APP)
        self.model = self.root / "pkg" / "mymodel"
        for d in ("model", "artifacts"):
            (self.model / d).mkdir(parents=True)
        (self.model / "param.yaml").write_text("task_type: detection\n")
        (self.model / "artifacts" / "net.bin").write_text("new")
        self.cfg = self.root / "my.yaml"; self.cfg.write_text("inputs: {}\n")

    def run_deploy(self, *args, **env):
        e = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", BOARD="board", MODEL_ZOO=str(self.zoo),
                 GST_APPS=str(self.root / "gst"), REMOTE_LOG=str(self.root / "run.log"), RUN_SECONDS="5")
        e.update(env)
        return subprocess.run(["bash", str(SCRIPT), *map(str, args)], env=e, capture_output=True, text=True)

    def test_installs_new_model(self):
        r = self.run_deploy(self.model)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.zoo / "mymodel" / "artifacts" / "net.bin").read_text(), "new")

    def test_refuses_to_overwrite_existing_model(self):
        (self.zoo / "mymodel").mkdir()
        (self.zoo / "mymodel" / "keep.txt").write_text("precious")
        r = self.run_deploy(self.model)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual((self.zoo / "mymodel" / "keep.txt").read_text(), "precious")
        self.assertFalse(list(self.zoo.glob(".incoming-*")), "nothing may be left staged")

    def test_replace_moves_old_to_backup_instead_of_deleting(self):
        (self.zoo / "mymodel").mkdir()
        (self.zoo / "mymodel" / "keep.txt").write_text("precious")
        r = self.run_deploy(self.model, REPLACE="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        backups = list(self.zoo.glob(".backup-mymodel-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "keep.txt").read_text(), "precious")
        self.assertTrue((self.zoo / "mymodel" / "param.yaml").exists())

    def test_application_failure_is_reported(self):
        r = self.run_deploy(self.model, self.cfg, FAKE_RC="7")
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertIn("exit status 7", r.stdout)

    def test_error_line_fails_even_with_exit_zero(self):
        r = self.run_deploy(self.model, self.cfg, FAKE_LOG="VX_ZONE_ERROR] boom")
        self.assertEqual(r.returncode, 5, r.stdout)

    def test_finite_input_timeout_is_failure_but_live_timeout_is_ok(self):
        self.assertEqual(self.run_deploy(self.model, self.cfg, FAKE_RC="124").returncode, 5)
        r = self.run_deploy(self.model, self.cfg, FAKE_RC="124", LIVE="1", REPLACE="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_clean_run_succeeds_and_existing_config_is_not_clobbered(self):
        r = self.run_deploy(self.model, self.cfg)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("RESULT: OK", r.stdout)
        # same config name again with a fresh model name -> config exists -> refuse
        other = self.root / "pkg" / "second"
        other.mkdir(parents=True)
        for d in ("model", "artifacts"):
            (other / d).mkdir()
        (other / "param.yaml").write_text("x: 1\n")
        r = self.run_deploy(other, self.cfg)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)

    def test_live_timeout_with_empty_log_is_a_failure(self):
        r = self.run_deploy(self.model, self.cfg, FAKE_RC="124", FAKE_NOLOG="1", LIVE="1")
        self.assertEqual(r.returncode, 5, r.stdout)
        self.assertIn("log is empty", r.stdout)

    def test_missing_offload_line_is_a_failure_unless_skipped(self):
        r = self.run_deploy(self.model, self.cfg, FAKE_LOG="something printed", FAKE_OFFLOAD="no offload info here")
        self.assertEqual(r.returncode, 5, r.stdout)
        self.assertIn("evidence the model loaded", r.stdout)
        r = self.run_deploy(self.model, self.cfg, FAKE_OFFLOAD="no offload info here", NO_OFFLOAD_CHECK="1", REPLACE="1")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_partial_offload_is_a_failure_unless_accepted(self):
        r = self.run_deploy(self.model, self.cfg, FAKE_OFFLOAD="Offloaded Nodes - 2, Total Nodes - 3")
        self.assertEqual(r.returncode, 5, r.stdout)
        self.assertIn("only 2 of 3", r.stdout)
        r = self.run_deploy(self.model, self.cfg, FAKE_OFFLOAD="Offloaded Nodes - 2, Total Nodes - 3", ALLOW_PARTIAL_OFFLOAD="1", REPLACE="1")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_zero_or_inconsistent_offload_counts_fail_even_when_partial_is_allowed(self):
        for line in ("Offloaded Nodes - 0, Total Nodes - 0", "Offloaded Nodes - 0, Total Nodes - 5", "Offloaded Nodes - 6, Total Nodes - 5"):
            with self.subTest(line=line):
                r = self.run_deploy(self.model, self.cfg, FAKE_OFFLOAD=line, ALLOW_PARTIAL_OFFLOAD="1", REPLACE="1")
                self.assertEqual(r.returncode, 5, r.stdout)
                self.assertIn("implausible offload counts", r.stdout)

    def test_note_when_frames_are_not_verified(self):
        r = self.run_deploy(self.model, self.cfg)
        self.assertIn("frame processing was not verified", r.stdout)

    def test_expected_output_must_be_written_during_the_run(self):
        out = self.root / "out"
        out.mkdir()
        r = self.run_deploy(self.model, self.cfg, EXPECT_OUTPUT=str(out / "f*.jpg"))
        self.assertEqual(r.returncode, 5, r.stdout)
        self.assertIn("no evidence frames were processed", r.stdout)
        r = self.run_deploy(self.model, self.cfg, EXPECT_OUTPUT=str(out / "f*.jpg"), FAKE_WRITE=str(out / "f1.jpg"), REPLACE="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("output files written during the run: 1", r.stdout)

    def test_config_collision_is_refused_before_anything_is_uploaded(self):
        (self.root / "gst" / "configs" / "my.yaml").write_text("existing\n")
        r = self.run_deploy(self.model, self.cfg)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertFalse((self.zoo / "mymodel").exists(), "the model must not be installed when the config would collide")
        self.assertFalse(list(self.zoo.glob(".incoming-*")))

    def test_rejects_non_model_folder(self):
        r = self.run_deploy(self.root)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
