# Rigor Checklist

Use this checklist before accepting any claim or report update.

## A. Pre-run

- [ ] Manifest fixed and recorded (`issue_set_id`, repo, dataset, track).
- [ ] Method settings locked (turn limits, prefixes, model).
- [ ] Track declared (`strict_commit_fidelity` or `same_snapshot_amortized`).
- [ ] Output location planned and reproducible.

## B. Run execution

- [ ] No silent run failures (inspect logs and `n_errors`).
- [ ] Repeats executed (`>=3` for primary claims).
- [ ] Repeat aggregate generated in `results/repeat_sets/`.

## C. Statistical readiness

- [ ] `min_repeats_met == true`
- [ ] `pairwise_bootstrap_available == true`
- [ ] `ci_ready == true`
- [ ] paired delta + bootstrap CI reported for primary comparison.

## D. Claim quality gates

- [ ] Claims use track-separated results (strict vs same-snapshot not mixed).
- [ ] Claims reference exact artifact paths.
- [ ] If CI spans zero, language is non-claiming ("inconclusive" or "not separable").
- [ ] Partial aggregates (e.g., 2 repeats) are labeled as partial.

## E. Documentation gates

- [ ] Report text only cites frozen artifacts.
- [ ] README numbers match frozen bundle.
- [ ] Handoff docs list unresolved risks and next concrete step.
- [ ] Attribution/provenance is explicit for adapted ideas/code.

