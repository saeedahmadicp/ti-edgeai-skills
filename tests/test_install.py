"""scripts/install.sh: right folders per agent/scope, never replaces unrelated things (HOME and cwd are temporary)."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "install.sh"
SKILLS = sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir())


class Install(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.cwd = Path(tempfile.mkdtemp())

    def run_install(self, *args):
        env = dict(os.environ, HOME=str(self.home))
        return subprocess.run(["bash", str(SCRIPT), *args], env=env, cwd=self.cwd, capture_output=True, text=True)

    def assert_linked(self, folder):
        for n in SKILLS:
            link = folder / n
            self.assertTrue(link.is_symlink(), f"{link} missing")
            self.assertEqual(os.readlink(link), str(ROOT / "skills" / n))

    def test_default_is_claude_user(self):
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_linked(self.home / ".claude" / "skills")

    def test_codex_user_scope(self):
        self.assertEqual(self.run_install("--agent", "codex").returncode, 0)
        self.assert_linked(self.home / ".agents" / "skills")

    def test_codex_repo_scope_uses_cwd_outside_git(self):
        self.assertEqual(self.run_install("--agent", "codex", "--scope", "repo").returncode, 0)
        self.assert_linked(self.cwd / ".agents" / "skills")

    def test_legacy_positional_target(self):
        t = self.home / "custom"
        self.assertEqual(self.run_install(str(t)).returncode, 0)
        self.assert_linked(t)

    def test_rerun_is_idempotent(self):
        self.run_install()
        r = self.run_install()
        self.assertEqual(r.returncode, 0)
        self.assertIn("already linked", r.stdout)

    def test_foreign_symlink_and_real_folder_are_not_replaced(self):
        folder = self.home / ".claude" / "skills"
        folder.mkdir(parents=True)
        other = self.home / "other"
        other.mkdir()
        (folder / SKILLS[0]).symlink_to(other)
        (folder / SKILLS[1]).mkdir()
        r = self.run_install()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(os.readlink(folder / SKILLS[0]), str(other))
        self.assertTrue((folder / SKILLS[1]).is_dir() and not (folder / SKILLS[1]).is_symlink())
        self.assertIn("not to this repository", r.stderr)
        # --force repoints the foreign symlink but still never touches the real folder
        r = self.run_install("--force")
        self.assertEqual(os.readlink(folder / SKILLS[0]), str(ROOT / "skills" / SKILLS[0]))
        self.assertTrue((folder / SKILLS[1]).is_dir() and not (folder / SKILLS[1]).is_symlink())
        self.assertEqual(r.returncode, 1)

    def test_dry_run_changes_nothing(self):
        r = self.run_install("--agent", "codex", "--dry-run")
        self.assertEqual(r.returncode, 0)
        self.assertIn("would link", r.stdout)
        self.assertFalse((self.home / ".agents").exists())

    def test_bad_options_fail(self):
        self.assertEqual(self.run_install("--agent", "vim").returncode, 2)
        self.assertEqual(self.run_install("--scope", "galaxy").returncode, 2)
        self.assertEqual(self.run_install("--nope").returncode, 2)


if __name__ == "__main__":
    unittest.main()
