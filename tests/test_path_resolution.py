import unittest

from src.path_resolution import canonicalize_file_path, canonicalize_file_paths


class PathResolutionTests(unittest.TestCase):
    def test_canonicalize_exact_and_suffix_match(self):
        valid = {
            "src/flask/app.py",
            "src/flask/helpers.py",
            "requests/sessions.py",
        }
        self.assertEqual(canonicalize_file_path("src/flask/app.py", valid), "src/flask/app.py")
        self.assertEqual(canonicalize_file_path("flask/helpers.py", valid), "src/flask/helpers.py")
        self.assertEqual(canonicalize_file_path("./requests/sessions.py", valid), "requests/sessions.py")

    def test_canonicalize_rejects_unknown_or_ambiguous(self):
        valid = {
            "a/path/common.py",
            "b/path/common.py",
        }
        self.assertIsNone(canonicalize_file_path("missing.py", valid))
        self.assertIsNone(canonicalize_file_path("common.py", valid))

    def test_canonicalize_list_deduplicates(self):
        valid = {
            "src/flask/app.py",
            "src/flask/helpers.py",
        }
        self.assertEqual(
            canonicalize_file_paths(
                ["flask/app.py", "src/flask/app.py", "flask/helpers.py", "missing.py"],
                valid,
            ),
            ["src/flask/app.py", "src/flask/helpers.py"],
        )


if __name__ == "__main__":
    unittest.main()
