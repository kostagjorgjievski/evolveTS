"""Explicit finite budgets; a live start is impossible without them."""
import hashlib
import json
import math
from pathlib import Path

SCHEMA_VERSION = 1

# Every field must be a finite positive number. A job whose config lacks any
# of these can be initialized and inspected, but `run`/`resume` refuse to
# launch a paid session.
REQUIRED_BUDGETS = (
    'model_session_seconds',   # per model session segment
    'job_wall_clock_seconds',  # whole-job wall clock, including waits
    'max_total_cost_usd',      # SDK-reported cost ceiling where measurable
    'max_tool_calls',          # dispatcher tool calls across the job
    'max_web_searches',        # bounded query budget
    'max_provider_retries',    # bounded provider retry count
    'retry_wait_seconds',      # wait between provider retries
)

DEFAULTS = {
    'schema_version': SCHEMA_VERSION,
    'enabled': False,
    'task': 'dfthcsos',
    'provider': {
        'name': 'minimax',
        'credential_file': '.credentials/minimax.env',
        'requested_model': 'MiniMax-M3.1-Flash[1m]',
        'requested_effort': 'medium',
    },
    'budgets': {
        'model_session_seconds': 12000,
        'job_wall_clock_seconds': 14400,
        'max_total_cost_usd': 25.0,
        'max_tool_calls': 600,
        'max_web_searches': 40,
        'max_provider_retries': 5,
        'retry_wait_seconds': 300,
    },
    'validation': {
        'max_development_attempts': 6,
        'development_salt_key': 'development_salt',
        'final_salt_key': 'final_salt',
        'improvement_margin': 0.0,          # both salts must exceed baseline + margin
        'conservative_comparison': 'both_salts',
    },
    'research': {
        'blocked_hosts': [],
        'allow_network_fetch': True,
        'max_sources': 200,
    },
    'queue': {'heavy_lock': 'work/runtime-locks/dqi-cpu.lock'},
    'publishing': {'library_snapshot': False},
    'production': {'automatic_enable': False},
}


class ConfigError(ValueError):
    pass


def _check_finite(budgets: dict, field: str) -> None:
    value = budgets.get(field)
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0):
        raise ConfigError(f'Budget {field} must be a finite positive number')


def validate(config: dict, *, require_enabled: bool = False) -> dict:
    if not isinstance(config, dict):
        raise ConfigError('Config must be a JSON object')
    if config.get('schema_version') != SCHEMA_VERSION:
        raise ConfigError('Unsupported config schema_version')
    enabled = config.get('enabled')
    if not isinstance(enabled, bool):
        raise ConfigError('enabled must be a boolean')
    if require_enabled and not enabled:
        raise ConfigError('Config is disabled; enable it explicitly to start a live job')
    budgets = config.get('budgets')
    if not isinstance(budgets, dict):
        raise ConfigError('budgets object required')
    missing = [field for field in REQUIRED_BUDGETS if field not in budgets]
    if missing:
        raise ConfigError('Missing required budgets: ' + ', '.join(missing))
    for field in REQUIRED_BUDGETS:
        _check_finite(budgets, field)
    provider = config.get('provider')
    if not isinstance(provider, dict):
        raise ConfigError('provider object required')
    for field in ('name', 'credential_file', 'requested_model'):
        if not isinstance(provider.get(field), str) or not provider[field].strip():
            raise ConfigError('provider.' + field + ' required')
    effort = provider.get('requested_effort', 'medium')
    if not isinstance(effort, str) or not effort.strip():
        raise ConfigError('provider.requested_effort must be a string when present')
    task = config.get('task')
    if not isinstance(task, str) or not task.replace('_', 'a').isalnum() or not task[0].isalpha() or not task[0].islower():
        raise ConfigError('task must be a lowercase task id')
    blocked = config.get('research', {}).get('blocked_hosts', [])
    parent_score = config.get('validation', {}).get('research_parent_score')
    if parent_score is not None and (isinstance(parent_score, bool)
            or not isinstance(parent_score, (int,float)) or not math.isfinite(parent_score) or parent_score <= 0):
        raise ConfigError('validation.research_parent_score must be finite and positive')
    if not isinstance(blocked, list) or not all(isinstance(host, str) for host in blocked):
        raise ConfigError('research.blocked_hosts must be a list of hostnames')
    if config.get('production', {}).get('automatic_enable'):
        raise ConfigError('production.automatic_enable must remain false')
    return config


def load(path, *, require_enabled: bool = False) -> dict:
    path = Path(path)
    try:
        config = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ConfigError(f'Config file not found: {path}') from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f'Config is not valid JSON: {exc}') from exc
    validate(config, require_enabled=require_enabled)
    return config


def config_digest(config: dict) -> str:
    return hashlib.sha256(canonical_config(config).encode()).hexdigest()


def canonical_config(config: dict) -> str:
    return json.dumps(config, sort_keys=True, ensure_ascii=False)
