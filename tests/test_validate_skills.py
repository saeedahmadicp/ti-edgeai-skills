"""The repository lint accepts every real skill and rejects a deliberately broken fixture."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINT = ROOT / "scripts" / "validate_skills.py"


def lint(*args):
    return subprocess.run([sys.executable, str(LINT), *args], capture_output=True, text=True)


class ValidateSkills(unittest.TestCase):
    def test_all_skills_pass(self):
        r = lint()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_bad_fixture_is_rejected_for_each_rule(self):
        r = lint(str(ROOT / "tests" / "fixtures" / "bad-skill"))
        self.assertEqual(r.returncode, 1)
        for needle in ["!= directory name", "does not exist", "not linked", "missing evals", "private IPv4", "absolute home path"]:
            self.assertIn(needle, r.stdout, needle)

    def test_bad_codex_metadata_is_rejected(self):
        import shutil
        import tempfile
        d = Path(tempfile.mkdtemp()) / "demo-skill"
        shutil.copytree(ROOT / "skills" / "ti-edgeai-dev", d)
        (d / "SKILL.md").write_text((d / "SKILL.md").read_text().replace("name: ti-edgeai-dev", "name: demo-skill"))
        (d / "agents" / "openai.yaml").write_text("interface:\n  display_name: X\n  short_description: Y\n  default_prompt: no skill mention\n")
        r = lint(str(d))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("default_prompt should mention $demo-skill", r.stdout)
        (d / "agents" / "openai.yaml").write_text("interface:\n  display_name: X\n")
        self.assertIn("needs interface.short_description", lint(str(d)).stdout)


if __name__ == "__main__":
    unittest.main()
