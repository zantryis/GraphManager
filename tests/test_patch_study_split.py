import unittest

from src.patch_study_split import allocate_verified_split, flatten_split


class PatchStudySplitTests(unittest.TestCase):
    def test_allocate_verified_split_is_deterministic(self):
        available = {
            "psf/requests": [f"r-{i}" for i in range(8)],
            "pytest-dev/pytest": [f"p-{i}" for i in range(19)],
            "pallets/flask": ["f-0"],
            "sympy/sympy": [f"s-{i}" for i in range(20)],
            "sphinx-doc/sphinx": [f"sp-{i}" for i in range(20)],
        }
        anchors = ["psf/requests", "pytest-dev/pytest", "pallets/flask"]
        caps = {
            "sympy/sympy": 12,
            "sphinx-doc/sphinx": 10,
        }
        target_n = 8 + 19 + 1 + 12 + 10

        split_a = allocate_verified_split(
            available_ids_by_repo=available,
            anchor_repos=anchors,
            capped_repos=caps,
            seed=17,
            target_n=target_n,
        )
        split_b = allocate_verified_split(
            available_ids_by_repo=available,
            anchor_repos=anchors,
            capped_repos=caps,
            seed=17,
            target_n=target_n,
        )

        self.assertEqual(split_a, split_b)
        self.assertEqual(len(split_a["psf/requests"]), 8)
        self.assertEqual(len(split_a["pallets/flask"]), 1)
        self.assertEqual(len(split_a["sympy/sympy"]), 12)
        self.assertEqual(len(flatten_split(split_a)), target_n)

    def test_allocate_verified_split_raises_on_target_mismatch(self):
        with self.assertRaises(ValueError):
            allocate_verified_split(
                available_ids_by_repo={"a/b": ["i1"]},
                anchor_repos=["a/b"],
                capped_repos={},
                seed=1,
                target_n=2,
            )


if __name__ == "__main__":
    unittest.main()

