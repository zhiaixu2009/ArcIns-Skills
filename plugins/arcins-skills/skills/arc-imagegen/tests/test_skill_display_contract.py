import unittest
from pathlib import Path


class SkillDisplayContractTests(unittest.TestCase):
    def test_requires_tool_preview_and_markdown_fallback(self):
        skill_path = Path(__file__).resolve().parents[1] / "SKILL.md"
        content = skill_path.read_text(encoding="utf-8")

        self.assertIn("`view_image`", content)
        self.assertIn("Markdown image embed", content)
        self.assertIn("absolute local path", content)
        self.assertNotIn("Do not use Markdown image embeds", content)


if __name__ == "__main__":
    unittest.main()
