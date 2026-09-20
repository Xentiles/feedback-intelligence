"""Exercise publication boundaries against a disposable real Git index."""

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import check_publication as publication


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        patcher = patch.object(publication, "REQUIRED", {"README.md"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.write("README.md", "public")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args])

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_excludes_ignored_local_template_but_rejects_force_staged_copy(self):
        self.write(".gitignore", "/orbital-clarity-v0.4/\n")
        self.write("orbital-clarity-v0.4/private.txt", "private template")
        files, problems = publication.inventory(self.root)
        self.assertFalse(problems)
        self.assertNotIn("orbital-clarity-v0.4/private.txt", [f["path"] for f in files])
        self.git("add", "-f", "orbital-clarity-v0.4/private.txt")
        self.assertTrue(
            any(
                "private or generated directory" in p
                for p in publication.inventory(self.root)[1]
            )
        )

    def test_index_check_reads_staged_blob_not_working_copy(self):
        self.git("add", "README.md")
        self.write("README.md", "different working copy")
        files, problems = publication.inventory(self.root, staged=True)
        self.assertFalse(problems)
        self.assertEqual(files[0]["sha256"], hashlib.sha256(b"public").hexdigest())

    def test_private_paths_and_external_data_are_blocked(self):
        for name in (
            "Project Plan Documentation/plan.md",
            ".env",
            "nested/DELETME.md",
            "data/external/olist/raw/reviews.csv",
            "data/processed/reviews.jsonl",
            "weights.gguf",
        ):
            with self.subTest(name=name):
                self.assertIsNotNone(publication.path_problem(name))
        for name in (
            ".env.example",
            ".env.development.example",
            "data/processed/README.md",
        ):
            self.assertIsNone(publication.path_problem(name))

    def test_rejects_symlinks_and_missing_required_files(self):
        (self.root / "README.md").unlink()
        (self.root / "linked").symlink_to("/tmp")
        _, problems = publication.inventory(self.root)
        self.assertTrue(
            any("required publication artifact missing" in p for p in problems)
        )
        self.assertTrue(any("non-regular file" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
