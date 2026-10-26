# Hermes checkpoint recovery

Time-bounded research jobs no longer inherit the low-level seeder template's lifetime 600-tool-call / 40-search ceilings. Their call counters remain recorded, with count limits disabled unless explicitly configured in the research service budget. The existing per-investigation model time, saved-window timer, daily admission and reported-cost ceilings remain enforced. Consumption is never reset during recovery. Generic standalone seeder jobs retain their explicit finite call limits.

Hermes receives `--max-turns 0`, the pinned upstream runtime's unlimited-turn setting. A tool count is not a model-turn count. The host clock still checkpoints the session at its authorized duration. Structured `failed: false` plus `max_iterations_reached(...)` on exit1 is treated as a saved checkpoint, while genuine provider errors remain failures.

An unexpected parallel worker failure now quarantines its owning investigation as infrastructure_blocked, preserving its session result and budget reservation. Other eligible investigations can continue. Status exposes requires_attention. Operators may explicitly configure service.pause_on_worker_failure if they require a global pause. Existing user PAUSE/STOP markers remain authoritative; recovery removes only the specifically diagnosed automatic marker.
