# Live 100-question evaluation, 24 Nov 2026

Isolated test copy (bu-ai-qa-api, own SQLite database, Claude claude-sonnet-5-5, same search settings as production).
Questions: ../fallback_test_100.json (36 Belhaven questions answered "couldn't find" on 19 Nov, 6 crisis/off-topic, 58 others).

- before_current_version_46ac745.json: today's demo code (+ test endpoint only), 14:44-14:55 UTC
- after_run1_7626bba.json: evidence-grounded answers, 15:47-15:58 UTC
- after_final_e805858.json: + crisis-wording and source-list fixes, 16:03-16:13 UTC
- manual_grades.py: one grade per answer from reading every before/after pair
The 19 Nov records are unchanged in ../original_live_test_2026-11-19.csv.
