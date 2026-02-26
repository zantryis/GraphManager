import unittest


class GenerateV2VerifiedManifestsTests(unittest.TestCase):
    def test_full_methods_match_expected_matrix(self):
        from tools.generate_v2_verified_manifests import FULL_METHODS

        expected = {
            "oracle",
            "gm_progressive",
            "rag_progressive",
            "gm_deterministic",
            "raw_rag_function",
            "raw_rag_fixed",
            "rag_metadata",
            "bm25",
            "agentic_cold_start",
            "repomap_like",
            "agentless_like_localization",
        }
        self.assertEqual(set(FULL_METHODS), expected)
        self.assertEqual(len(FULL_METHODS), 11)

    def test_manifest_payload_rag_tool_flag_behavior(self):
        from tools.generate_v2_verified_manifests import _manifest_payload

        rag_payload = _manifest_payload(
            repo="psf/requests",
            retrieval_method="rag_progressive",
            instance_ids=["psf__requests-1"],
        )
        self.assertTrue(rag_payload.get("rag_symmetric_tools"))

        raw_payload = _manifest_payload(
            repo="psf/requests",
            retrieval_method="raw_rag_function",
            instance_ids=["psf__requests-1"],
        )
        self.assertFalse(raw_payload.get("rag_symmetric_tools"))

        rag_metadata_payload = _manifest_payload(
            repo="psf/requests",
            retrieval_method="rag_metadata",
            instance_ids=["psf__requests-1"],
        )
        self.assertFalse(rag_metadata_payload.get("rag_symmetric_tools"))

        oracle_payload = _manifest_payload(
            repo="psf/requests",
            retrieval_method="oracle",
            instance_ids=["psf__requests-1"],
        )
        self.assertNotIn("rag_symmetric_tools", oracle_payload)


if __name__ == "__main__":
    unittest.main()
