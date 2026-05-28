# Codebase Introspection Report

**Generated:** 2026-05-04T09:32:22.854277+00:00

## Summary

- **Total Modules:** 272
- **Total Functions:** 1518
- **Total Classes:** 424
- **Average Coverage:** 0.0%

## Complexity Distribution

- **LOW:** 1361
- **MEDIUM:** 157
- **HIGH:** 0
- **CRITICAL:** 0

## Severity Summary

- **P1:** 16
- **P2:** 37
- **P3:** 1379

## Error Handling Gaps

**Total Gaps:** 16

### Top 20 Gaps

| Function | File | Gap Type | Recommendation |
|----------|------|----------|----------------|
| run | reasoner_persuasion_defense.py | no_handling | Add try/except block around I/O operations |
| reset_all_quotas_monthly | api\cron.py | no_handling | Add try/except block around I/O operations |
| error_logs | api\__init__.py | no_handling | Add try/except block around I/O operations |
| add | core\memory.py | no_handling | Add try/except block around I/O operations |
| get_quota | infrastructure\persistence\quota_repo_postgres.py | no_handling | Add try/except block around I/O operations |
| check_and_increment | infrastructure\persistence\quota_repo_postgres.py | no_handling | Add try/except block around I/O operations |
| reset_monthly | infrastructure\persistence\quota_repo_postgres.py | no_handling | Add try/except block around I/O operations |
| log_query | infrastructure\persistence\quota_repo_postgres.py | no_handling | Add try/except block around I/O operations |
| upsert_subscription | infrastructure\persistence\subscription_repo.py | no_handling | Add try/except block around I/O operations |
| sync_quota_for_subscription | infrastructure\persistence\subscription_repo.py | no_handling | Add try/except block around I/O operations |
| set_subscription_status | infrastructure\persistence\subscription_repo.py | no_handling | Add try/except block around I/O operations |
| set_subscription_status_by_paypal | infrastructure\persistence\subscription_repo.py | no_handling | Add try/except block around I/O operations |
| execute | subagents\critique\hyper_agent.py | no_handling | Add try/except block around I/O operations |
| execute | subagents\decomposition\hyper_agent.py | no_handling | Add try/except block around I/O operations |
| execute | subagents\enhancement\hyper_agent.py | no_handling | Add try/except block around I/O operations |
| execute | subagents\search\hyper_agent.py | no_handling | Add try/except block around I/O operations |

## Type Annotation Gaps

**Total Gaps:** 37

### Top 20 Gaps

| Function | File | Missing Annotations |
|----------|------|---------------------|
| check_component | server_check.py | name, func |
| dispatch | api\middleware.py | self, request, call_next |
| dispatch | api\middleware.py | self, request, call_next |
| dispatch | api\middleware.py | self, request, call_next |
| dispatch | api\middleware.py | self, request, call_next |
| run_pipeline | api\__init__.py | request, req, user, authenticated, rate_limit_checked, quota, csrf_checked |
| run_followup_pipeline | api\__init__.py | request, req, user, rate_limit_checked, csrf_checked |
| search_web | api\__init__.py | req, user, rate_limit_checked |
| clear_cache | api\__init__.py | csrf_checked |
| stop_pipeline | api\__init__.py | run_id, user, csrf_checked |
| estimate_cost | api\__init__.py | req, csrf_checked |
| submit_feedback | api\__init__.py | req, csrf_checked |
| run_with_context | api\routes\context.py | req, user, rate_limit_checked, csrf_checked, quota |
| delete_history_entry | api\routes\history.py | entry_id, user, csrf_checked |
| clear_history | api\routes\history.py | user, csrf_checked |
| generate_image_endpoint | api\routes\images.py | request, body, user, rate_limit_checked, csrf_checked, quota |
| get_api_keys_status | api\routes\keys.py | user, authenticated |
| validate_api_keys | api\routes\keys.py | request, authenticated, csrf_checked |
| calculate | api\routes\legacy_widgets.py | req, csrf_checked |
| resume_pipeline | api\routes\pipelines.py | pipeline_id, user, csrf_checked |

## Dead Code

**Total Items:** 1379

### Top 20 Items

| Type | Name | File | Reason |
|------|------|------|--------|
| function | authorize | auth.py | Public function not called anywhere in codebase |
| function | check_scopes | auth.py | Public function not called anywhere in codebase |
| function | revoke_key | auth.py | Public function not called anywhere in codebase |
| function | list_keys | auth.py | Public function not called anywhere in codebase |
| function | get_rate_limit_tier | auth.py | Public function not called anywhere in codebase |
| function | state | circuit_breaker.py | Public function not called anywhere in codebase |
| function | stats | circuit_breaker.py | Public function not called anywhere in codebase |
| function | reset_all_circuits | circuit_breaker.py | Public function not called anywhere in codebase |
| function | decide | gate_agent.py | Public function not called anywhere in codebase |
| function | filter | logging_utils.py | Public function not called anywhere in codebase |
| function | set_correlation_id | logging_utils.py | Public function not called anywhere in codebase |
| function | critical | logging_utils.py | Public function not called anywhere in codebase |
| function | timed_async | logging_utils.py | Public function not called anywhere in codebase |
| function | configure_logging | logging_utils.py | Public function not called anywhere in codebase |
| function | total | models.py | Public function not called anywhere in codebase |
| function | total | models.py | Public function not called anywhere in codebase |
| function | synthesis | models.py | Public function not called anywhere in codebase |
| function | total_cost_usd | models.py | Public function not called anywhere in codebase |
| function | phase_costs | models.py | Public function not called anywhere in codebase |
| function | detailed_token_usage | models.py | Public function not called anywhere in codebase |
