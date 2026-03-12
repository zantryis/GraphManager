# Claims Lock (V2 — Updated after full statistical analysis)

Status: Active for Paper 1 drafting. Last updated: 2026-03-12.
Previous version: 2026-02-25 (V1 exploratory framing — now superseded by V2 confirmatory data).

This file constrains claim strength and phrasing for the current evidence state.

## Evidence Summary

- **N = 500** SWE-bench Verified instances, 12 repositories, 11 methods + oracle
- **McNemar pairwise tests**: GM-P vs all 9 baselines, all significant after Holm-Bonferroni (α=0.05)
- **Weakest corrected p**: GM-P vs RAG-Progressive, p_holm = 0.036
- **Effect sizes**: Cohen's h range 0.10 (vs RRX) to 0.99 (vs RPM)

## Updated Claims Table

| Claim | Status | Allowed wording | NOT allowed |
|---|---|---|---|
| GM-P highest resolve rate among non-oracle methods | ALLOW | "GM-P achieved the highest observed resolve rate (46.8%) among the evaluated non-oracle methods on this benchmark" | "GM-P is the best method in general" |
| GM-P vs specific baselines | ALLOW | "GM-P achieved a higher resolve rate than [method] on this benchmark; paired McNemar test significant after Holm correction" | "GM-P dominates all alternatives across settings" |
| Statistical comparison claims | ALLOW WITH QUALIFIERS | "Paired differences significant under McNemar tests with Holm-Bonferroni correction" | Unqualified "significantly better" without benchmark scope |
| Cost efficiency | ALLOW | "GM-P's per-resolved-issue cost is ~7.5× lower than RAG-Progressive" | "GM-P is the cheapest method" (BM25/ACS are cheaper) |
| Pareto frontier | ALLOW | "GM-P occupies the Pareto frontier of cost and effectiveness among the evaluated methods" | Unqualified "Pareto dominant" without method scope |
| Generalization | DO NOT ALLOW | "Results observed on this benchmark of 500 instances from 12 Python repositories" | "Will perform better on real-world repositories broadly" |
| RepoMap-Like | ALLOW WITH CAVEAT | "Our PageRank-based implementation performed poorly; this result should be interpreted cautiously" | "RepoMap-style methods do not work" |
| Agentless-Like | ALLOW WITH CAVEAT | "Our adapted implementation uses the GM graph in Stage 2; results reflect our adaptation, not original Agentless" | "We beat Agentless" |
| Oracle | CONTEXT ONLY | "Oracle achieved 53.8%, providing an approximate ceiling" | Implying Oracle is a deployable baseline |
| "Confirmatory" | DO NOT ALLOW | "Inferential evidence on this benchmark supports higher paired success rates" | "This is a confirmatory study" (hypotheses not pre-registered) |

## Required Disclosures

1. **Dual-build**: Both graph and RAG indices were built in the harness; cost is method-accounted.
2. **Single run**: One run per method; McNemar tests valid for observed outcomes but do not capture LLM sampling variance.
3. **Proxy implementations**: "-Like" baselines are controlled re-implementations, not faithful reproductions.
4. **Within-repo clustering**: 500 instances from 12 repos; possible clustering effects not modeled.
5. **Embedding in graph**: GM framework uses embeddings for node metadata (FAISS); "embedding-free" refers to runtime query phase, not build time.
