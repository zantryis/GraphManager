# GraphManager — canonical build/check targets
# Usage: make verify  (health check before any work)
#        make smoke    (quick end-to-end validation)
#        make test     (full test suite)

.PHONY: verify test smoke lint clean help

PYTHON := ./.venv/bin/python

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

verify: test lint ## Full health check (run before any code change)
	@echo ""
	@echo "=== VERIFY PASSED ==="

test: ## Run full test suite (242 tests)
	$(PYTHON) -m unittest discover -s tests -v

lint: ## Check for import errors and syntax issues
	$(PYTHON) -c "import src.evaluation; import src.patch_agent; import src.graph_builder; import src.bm25_baseline; import src.agentic_cold_start; import src.repomap_like; import src.agentless_like_localization; print('All imports OK')"
	$(PYTHON) -c "import run_patch; import run_experiment; print('Entrypoints OK')"

smoke: ## Quick smoke test: dry-run patch on 1 instance (no API key needed)
	@echo "Smoke test: verifying pipeline plumbing (dry-run, no API calls)..."
	@$(PYTHON) -c "\
	from run_patch import _capture_provenance, _cap_retrieved_files, _compute_patch_robustness_metrics; \
	prov = _capture_provenance('Makefile'); \
	assert 'pipeline_git_sha' in prov, 'provenance missing git sha'; \
	assert 'manifest_sha256' in prov, 'provenance missing manifest hash'; \
	files, pre, post = _cap_retrieved_files(['a.py','b.py','c.py'], max_files=2); \
	assert len(files) == 2 and pre == 3 and post == 2, 'cap logic broken'; \
	metrics = _compute_patch_robustness_metrics([{'patch_status':'patched'},{'patch_status':'no_patch'}]); \
	assert metrics['n_apply_ok'] == 1, 'robustness metrics broken'; \
	print('Smoke test PASSED');"

clean: ## Remove Python caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
