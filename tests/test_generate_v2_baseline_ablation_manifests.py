import unittest


class GenerateV2BaselineAblationManifestTests(unittest.TestCase):
    def test_profile_catalog_contains_research_ablation_axes(self):
        from tools.generate_v2_baseline_ablation_manifests import ABLATION_PROFILES

        for name in (
            "repomap_base",
            "repomap_map512",
            "repomap_map2000",
            "repomap_no_personalization",
            "agentless_stage1_only",
            "agentless_stage12",
            "agentless_full",
        ):
            self.assertIn(name, ABLATION_PROFILES)

    def test_profiles_bind_expected_retrieval_methods(self):
        from tools.generate_v2_baseline_ablation_manifests import ABLATION_PROFILES

        for name, payload in ABLATION_PROFILES.items():
            method = payload.get("retrieval_method")
            if name.startswith("repomap_"):
                self.assertEqual(method, "repomap_like")
            if name.startswith("agentless_"):
                self.assertEqual(method, "agentless_like_localization")


if __name__ == "__main__":
    unittest.main()
