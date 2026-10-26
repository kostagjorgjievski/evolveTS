# Hermes public-source freshness

The deterministic source watcher is separate from paid model admission and reproducer backpressure. It checks the competition's anonymous public notebook listing every 1,800 seconds, paginates until exhausted, validates URL/version fields, saves raw metadata and queues new/updated versions for each benchmark's model-led interpretation. It does not implement candidate algorithms or certify reported scores. Both agendas retain their existing independent paid budgets.

`source-watch/status.json` records last attempt, last successful check, next attempt, coverage, new versions and consecutive failures. HTTP200 HTML shells, malformed/empty first pages, repeated pagination and incomplete coverage cannot count as success. Failure preserves the previous successful timestamp, sets `requires_attention`, and retries after300 seconds. It never infers authentication requirements. The model's Kaggle `report_access_needed` now records `retrieval_unresolved` and an explicitly unverified claim. Actual access controls remain respected.

Paper-discovery topics are removed from continuous topic rotation and queued once per UTC day by this watcher. Existing investigations continue; follow-through/reproduction is not restricted to daily operation. No active model is interrupted to adopt these changes. New tool processes load the revised access-report behavior.

Run `python -m scripts.autoresearch_seeder.source_watch WATCH_DIRECTORY DQI_ROOT CHEMISTRY_ROOT` from the isolated implementation checkout. Its exclusive lock prevents duplicate watchers. This is project runtime infrastructure; it does not recreate the deleted Codex scheduled monitor. Status is available on disk; it does not send automatic user notifications.
