"""AutoResearch seeder: task-isolated autonomous researcher producing verified seeds.

Module boundaries (see docs/autoresearch-seeder.md):
  models      stable entities, canonical hashing, bundle freezing
  config      explicit budgets; missing budgets prevent a live start
  store       job-scoped durable research store (sources/hypotheses/experiments)
  adapter     task contracts loaded from tasks/<id>/library.json
  tools       the worker tool dispatcher shared by offline tests and the MCP server
  transport   model transports (deterministic fake for tests, SDK-backed for live)
  worker      one research session: prepared context -> tool loop -> outcome
  controller  durable jobs, leases, budgets, stage machine, recovery
  publisher   machine-checkable acceptance gates and immutable seed export
  context     prepared-context construction for fresh conversations
  mcp_server  stdio MCP shim exposing the dispatcher to a live model session
"""
ROOT = __import__('pathlib').Path(__file__).resolve().parents[2]
