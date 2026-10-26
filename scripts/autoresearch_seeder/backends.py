"""Researcher backends: how a model session talks to the seeder's MCP tools.

The seeder controller is backend-agnostic: every backend exposes
`run(prompt, tools, workspace, budget) -> TransportResult` plus `preflight()`
and `metadata()`. Backends never implement scoring, validation or storage —
those stay in the trusted task adapter, dispatcher and controller. All
backends spawn the SAME dispatcher MCP server, so a Claude Code session and a
Hermes session receive identical trusted tools.
"""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import ROOT
from .models import ProviderRateLimit, ToolInfrastructureError
from .transport import TransportResult, classify_provider_error, provider_error_detail

INTERPRETER_PROBE = (
    'import sys, json; import mcp; from mcp.server.stdio import stdio_server; '
    'print(json.dumps([path for path in sys.path if path]))')

_INTERPRETER_CACHE = {}


def resolve_interpreter(app_root=None) -> Path:
    """An explicit Python interpreter that can run the seeder MCP server.

    Preference: the checkout's own virtualenv, then the current interpreter.
    The choice is validated once per process by actually importing `mcp` in a
    subprocess; an interpreter without the required dependencies is rejected
    with a clear message instead of failing mid-session.
    """
    root = Path(app_root) if app_root else ROOT
    candidates = []
    venv = root / '.venv/bin/python'
    if venv.is_file():
        candidates.append(venv)
    current = Path(sys.executable)
    if current not in candidates:
        candidates.append(current)
    for candidate in candidates:
        key = str(candidate)
        if key in _INTERPRETER_CACHE:
            if _INTERPRETER_CACHE[key]['ok']:
                return candidate
            continue
        try:
            probe = subprocess.run(
                [str(candidate), '-c', INTERPRETER_PROBE],
                capture_output=True, timeout=60, text=True,
                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
            ok = probe.returncode == 0
            sys_path = []
            if ok:
                try:
                    sys_path = json.loads(probe.stdout.strip().splitlines()[-1])
                    ok = isinstance(sys_path, list)
                except (ValueError, IndexError):
                    ok = False
        except (subprocess.SubprocessError, OSError):
            ok = False
            sys_path = []
        _INTERPRETER_CACHE[key] = {'ok': bool(ok), 'sys_path': sys_path or []}
        if ok:
            return candidate
    raise ToolInfrastructureError(
        'No Python interpreter with the `mcp` package is available for the '
        'seeder MCP server. Tried: '
        + ', '.join(str(candidate) for candidate in candidates)
        + '. Install the runtime dependencies (e.g. `pip install mcp`) into '
          'one of them.')


def interpreter_sys_path(app_root=None) -> list:
    """The import paths the validated interpreter actually resolves `mcp` by.

    Captured during the validation probe — NOT reconstructed from this
    process's site module, which describes a different interpreter on
    machines where the test runner and the resolved server interpreter
    differ. This is exactly what the MCP server child needs to import `mcp`
    under a scrubbed HOME.
    """
    interpreter = resolve_interpreter(app_root)
    return list(_INTERPRETER_CACHE[str(interpreter)]['sys_path'])


def server_env(app_root=None) -> dict:
    """Clean child environment that still resolves the interpreter's packages.

    HOME is scrubbed so nothing user-local leaks into the server process;
    package resolution survives because PYTHONPATH carries the validated
    interpreter's own import paths (explicit entries bypass user-site
    resolution that would otherwise follow the scrubbed HOME).
    """
    directories = []
    for directory in interpreter_sys_path(app_root):
        if directory and directory not in directories and Path(directory).is_dir():
            directories.append(directory)
    return {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent',
            'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONPATH': os.pathsep.join(directories)}


def mcp_server_command(job_dir, app_root=None) -> list:
    """The dispatcher command every backend spawns for its model session."""
    return [str(resolve_interpreter(app_root)),
            str(Path(__file__).with_name('mcp_server.py')), str(job_dir)]


def credential_path(app_root, credential_file) -> Path:
    """Credential files are resolved from an explicit application root."""
    path = Path(credential_file)
    return path if path.is_absolute() else Path(app_root) / path


def load_environment(path) -> dict:
    """Parse an env file the way run_worker.environment does."""
    import shlex
    values = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line.startswith('export '):
            line = line[7:]
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        if key.replace('_', '').isalnum():
            fields = shlex.split(value, comments=True)
            if len(fields) == 1:
                values[key] = fields[0]
    return values


class Backend:
    name = 'backend'

    def preflight(self) -> list:
        """[{'check':..., 'ok':..., 'detail':...}] — no secrets in details."""
        raise NotImplementedError

    def metadata(self) -> dict:
        """Requested vs served model/effort information for the record."""
        raise NotImplementedError

    def run(self, prompt, tools, workspace, budget) -> TransportResult:
        raise NotImplementedError


def session_metadata(requested_model, requested_effort, served_models,
                     effort_attested=False) -> dict:
    """Honest model/effort metadata: requested is config, served is observed.

    Effort is recorded as requested-only unless the provider explicitly
    attests what it served; the seeder never claims the provider honored an
    effort value it cannot verify.
    """
    return {'requested_model': requested_model,
            'requested_effort': requested_effort,
            'served_models': sorted(set(served_models or [])),
            'effort_attested': bool(effort_attested),
            'note': 'Requested values come from configuration; served models '
                    'are observed from provider responses. Effort honoring is '
                    'not independently attested.'}


# Hermes Agent release whose official documentation (hermes-agent.nousresearch.com,
# fetched 2026-10-25) this backend was written against. The exact version reported
# by the installed binary is recorded in job metadata at preflight time.
HERMES_PIN = {'release': 'v0.22.5',
              'commit': 'bf0203a794a07aac3ff764972ab9087baa4e4f4e',
              'docs_verified': '2026-10-25'}


def _yaml_dump(mapping) -> str:
    """Minimal YAML emitter for the flat/dict/list values we write.

    Hermes configuration files are YAML; depending on PyYAML here would add a
    hard dependency to every job, so emit the small subset we need directly.
    Values are JSON-compatible scalars/lists/mappings, quoted when ambiguous.
    """
    import json as _json

    def scalar(item):
        if isinstance(item, bool):
            return 'true' if item else 'false'
        if isinstance(item, (int, float)):
            return str(item)
        return _json.dumps(str(item))

    def render(value, indent) -> list:
        pad = ' ' * indent
        if isinstance(value, dict):
            if not value:
                return [pad.rstrip() + ' {}' if pad else '{}']
            lines = []
            for key, item in value.items():
                if isinstance(item, (dict, list)) and item:
                    lines.append(f'{pad}{key}:')
                    lines.extend(render(item, indent + 2))
                else:
                    lines.append(f'{pad}{key}: ' + ' '.join(render(item, 0)))
            return lines
        if isinstance(value, list):
            return [f'{pad}- {scalar(item)}' for item in value]
        return [scalar(value)]

    return '\n'.join(render(mapping, 0)) + '\n'


class HermesBackend(Backend):
    """Optional researcher backend driving the Hermes Agent CLI (Nous Research).

    Same trust model as the Claude Code backend: the agent loop, MCP tool
    filtering and provider transport happen inside Hermes, while every tool
    call still executes in the seeder's dispatcher MCP server child (identical
    validated interpreter, identical job store) — so experiments, budgets and
    receipts are recorded by trusted code regardless of backend.

    Verified-against-docs configuration (hermes-agent.nousresearch.com,
    release v0.22.5, docs fetched 2026-10-25):
      * `hermes chat --oneshot --quiet --format stream-json --usage-file PATH
         --query-file PATH --provider custom:<name> -m <model> --in <dir>
         --ignore-rules` — headless single session.
      * `$HERMES_HOME/config.yaml` + `$HERMES_HOME/.env` — per-job isolated
        profile directory (no shared global memory between jobs).
      * `providers.<name>` with `api` / `key_env` / `transport` and
        `model.provider: custom:<name>` — named custom endpoint; the GLM
        endpoint is Anthropic-compatible, so `transport: anthropic_messages`.
      * `mcp_servers.<name>` stdio entries (`command` / `args` / `env`) with
        `tools.include` filtering on original (unsanitized) tool names.
      * `agent.reasoning_effort` — requested effort in config.

    Flags deliberately NOT passed: `--ignore-user-config` (it would discard
    the per-job provider/MCP configuration this backend relies on; isolation
    comes from HERMES_HOME itself) and `--safe-mode` (same reason — it
    disables ALL customizations including ours).
    """

    name = 'hermes'

    def __init__(self, provider_config, job_dir, app_root=None,
                 hermes_bin=None, version_timeout=30):
        from .tools import TOOL_SCHEMAS
        self.provider = provider_config
        self.job_dir = Path(job_dir)
        self.app_root = Path(app_root) if app_root else ROOT
        self.hermes_bin_setting = hermes_bin or provider_config.get('hermes_bin')
        self.version_timeout = version_timeout
        self.tool_names = sorted(TOOL_SCHEMAS)
        self.served_models = []
        self.reported_version = ''
        self.home = self.job_dir / 'private' / 'hermes-home'
        self.provider_name = provider_config.get('provider_name', 'seeder_glm')
        self.credential_file = credential_path(
            self.app_root, provider_config['credential_file'])
        self._home_written = False

    # -- profile directory ---------------------------------------------------

    def _credentials(self) -> dict:
        if not self.credential_file.is_file():
            return {}
        return load_environment(self.credential_file)

    def _endpoint(self, credentials) -> tuple:
        """(api base URL, api key, transport) — never logged with the key."""
        api_key = credentials.get(self.provider.get('api_key_env',
                                                    'ANTHROPIC_AUTH_TOKEN'), '')
        endpoint = self.provider.get('endpoint_url') \
            or credentials.get('ANTHROPIC_BASE_URL', '')
        transport = self.provider.get('wire_transport', 'anthropic_messages')
        return endpoint, api_key, transport

    def write_home(self) -> dict:
        """(Re)write the isolated per-job Hermes profile directory.

        Everything Hermes persists — config, secrets, sessions, memories —
        lives under this job-local directory, so two jobs share nothing and
        no global agent memory leaks between them. Secrets land only in
        $HERMES_HOME/.env with mode 0600.
        """
        credentials = self._credentials()
        endpoint, api_key, transport = self._endpoint(credentials)
        server = mcp_server_command(self.job_dir, self.app_root)
        env = server_env(self.app_root)
        env['SEEDER_ALLOWED_TOOLS']=json.dumps(self.tool_names)
        model = self.provider.get('requested_model') \
            or credentials.get('ANTHROPIC_MODEL', '')
        effort = self.provider.get('requested_effort', 'medium')
        key_env = self.provider.get('key_env', 'SEEDER_GLM_API_KEY')
        self.home.mkdir(mode=0o700, parents=True, exist_ok=True)
        config = {
            'model': {'provider': f'custom:{self.provider_name}',
                      'default': model},
            'agent': {'reasoning_effort': effort, 'run_budget_seconds': self.provider.get('session_seconds', 1200)},
            'providers': {self.provider_name: {
                'api': endpoint, 'key_env': key_env, 'transport': transport}},
            'mcp_servers': {'seeder': {
                'command': server[0], 'args': server[1:], 'env': env,
                'tools': {'include': self.tool_names,
                          'resources': False, 'prompts': False}}},
        }
        (self.home / 'config.yaml').write_text(_yaml_dump(config))
        (self.home / 'config.yaml').chmod(0o600)
        env_file = self.home / '.env'
        env_file.write_text(f'{key_env}={api_key}\n' if api_key else '')
        env_file.chmod(0o600)
        self._home_written = True
        return {'endpoint': endpoint, 'transport': transport, 'model': model,
                'has_key': bool(api_key), 'key_env': key_env}

    def home_summary(self) -> dict:
        """Config echo for metadata — describes the profile, never the key."""
        credentials = self._credentials()
        endpoint, api_key, transport = self._endpoint(credentials)
        return {'hermes_home': str(self.home),
                'provider': f'custom:{self.provider_name}',
                'endpoint': endpoint, 'wire_transport': transport,
                'mcp_server': 'seeder (stdio, tools.include filtered)',
                'reasoning_effort': self.provider.get('requested_effort', 'medium')}

    # -- Backend interface ---------------------------------------------------

    def resolve_binary(self) -> str:
        import shutil
        resolved = shutil.which(self.hermes_bin_setting or 'hermes')
        if not resolved:
            raise ToolInfrastructureError(
                'Hermes CLI not found. The optional Hermes backend requires the '
                'Hermes Agent CLI (Nous Research, pinned release '
                + self.pinned_release() + ') on PATH or set provider.hermes_bin. '
                'Install it on the evaluation machine; this is a prerequisite, '
                'not something the seeder installs.')
        return resolved

    def pinned_release(self) -> str:
        """The release this deployment is verified against (config overridable)."""
        return str(self.provider.get('hermes_pin') or HERMES_PIN['release'])

    @staticmethod
    def _version_token(text) -> str:
        """Extract the release number from `hermes --version` output.

        Prefers a v-prefixed token (e.g. `hermes-client-v0.22.5`), then any
        bare numeric release; returns '' when nothing parseable is present.
        """
        import re
        v_prefixed = re.findall(r'v(\d+\.\d+(?:\.\d+)?)', text or '')
        if v_prefixed:
            return v_prefixed[-1]
        bare = re.findall(r'\b(\d+\.\d+(?:\.\d+)?)\b', text or '')
        return bare[-1] if bare else ''

    def probe_version(self) -> str:
        binary = self.resolve_binary()
        try:
            interpreter=Path(binary).parent/'python'
            command=([str(interpreter),'-c','from hermes_cli._startup_fast import print_fast_version_info; print_fast_version_info(check_updates=False)']
                     if interpreter.is_file() else [binary,'--version'])
            probe = subprocess.run(command, capture_output=True,
                                   text=True, timeout=self.version_timeout,
                                   env={**os.environ, 'HERMES_HOME': str(self.home)})
            self.reported_version = (probe.stdout + probe.stderr).strip()[:200]
        except (subprocess.SubprocessError, OSError) as exc:
            self.reported_version = ''
            raise ToolInfrastructureError(
                f'Hermes CLI found at {binary} but --version failed: {exc}')
        return self.reported_version

    def preflight(self) -> list:
        checks = []
        if not self.credential_file.is_file():
            checks.append({'check': f'credential file present '
                                    f'({self.credential_file})', 'ok': False,
                           'detail': 'Configure the provider credential file; '
                                     'contents are never printed'})
        else:
            checks.append({'check': f'credential file present '
                                    f'({self.credential_file})', 'ok': True})
        credentials = self._credentials()
        _, api_key, _ = self._endpoint(credentials)
        checks.append({'check': 'provider API key present in credential file',
                       'ok': bool(api_key),
                       'detail': '' if api_key else
                       'The credential file must define the provider API key '
                       '(value never printed)'})
        try:
            binary = self.resolve_binary()
            checks.append({'check': f'Hermes CLI present ({binary})', 'ok': True})
            try:
                version = self.probe_version()
                found = self._version_token(version)
                pinned = self._version_token(self.pinned_release()) \
                    or self.pinned_release().lstrip('v')
                if not found:
                    checks.append({
                        'check': f'Hermes version matches pinned release '
                                 f'({self.pinned_release()})', 'ok': False,
                        'detail': f'could not parse a version from '
                                  f'`--version` output: {version[:120]!r}'})
                elif found == pinned:
                    checks.append({'check': f'Hermes CLI version ({version})',
                                   'ok': True,
                                   'detail': f'matches pinned release '
                                             f'{self.pinned_release()} '
                                             f'(docs '
                                             f'{HERMES_PIN["docs_verified"]})'})
                else:
                    checks.append({
                        'check': f'Hermes version matches pinned release '
                                 f'({self.pinned_release()})', 'ok': False,
                        'detail': f'installed version {found} != pinned '
                                  f'{pinned}. Install the pinned release '
                                  f'from the official source at tag v{pinned} '
                                  f'or re-verify against the new release and '
                                  f'update provider.hermes_pin deliberately.'})
            except ToolInfrastructureError as exc:
                checks.append({'check': 'Hermes CLI --version', 'ok': False,
                               'detail': str(exc)})
        except ToolInfrastructureError as exc:
            checks.append({'check': 'Hermes CLI present', 'ok': False,
                           'detail': str(exc)})
        try:
            endpoint, _, transport = self._endpoint(credentials)
            checks.append({'check': 'custom endpoint URL configured', 'ok': bool(endpoint),
                           'detail': '' if endpoint else
                           'Set provider.endpoint_url or ANTHROPIC_BASE_URL in '
                           'the credential file'})
            checks.append({'check': f'wire transport supported ({transport})',
                           'ok': transport in ('anthropic_messages',
                                               'chat_completions'),
                           'detail': 'Hermes named providers support '
                                     'anthropic_messages and chat_completions'})
        except Exception as exc:  # defensive: configuration errors must be visible
            checks.append({'check': 'provider configuration parseable', 'ok': False,
                           'detail': str(exc)})
        try:
            summary = self.write_home()
            checks.append({'check': f'isolated Hermes home written '
                                    f'({self.home})', 'ok': True,
                           'detail': f'endpoint {summary["endpoint"]} via '
                                     f'{summary["transport"]}'})
        except ToolInfrastructureError as exc:
            checks.append({'check': 'isolated Hermes home written', 'ok': False,
                           'detail': str(exc)})
        try:
            mcp_server_command(self.job_dir, self.app_root)
            checks.append({'check': 'MCP server interpreter validated', 'ok': True})
        except ToolInfrastructureError as exc:
            checks.append({'check': 'MCP server interpreter validated', 'ok': False,
                           'detail': str(exc)})
        if not self.provider.get('requested_model'):
            checks.append({'check': 'requested model configured', 'ok': False,
                           'detail': 'provider.requested_model is required '
                                     '(no silent fallback to a default model)'})
        return checks

    def metadata(self):
        info = session_metadata(
            self.provider.get('requested_model'),
            self.provider.get('requested_effort'),
            self.served_models)
        info.update({'backend': self.name, 'hermes_pin': dict(HERMES_PIN),
                     'hermes_pin_enforced': self.pinned_release(),
                     'hermes_reported_version': self.reported_version,
                     'hermes_reported_release': self._version_token(
                         self.reported_version),
                     'hermes_home': self.home_summary(),
                     'usage_source': 'hermes --usage-file JSON (provider-reported '
                                     'tokens/cost; post-hoc, not a spend limiter)'})
        return info

    def _stop_owner(self, binary, env):
        record=self.home/'gateway.pid'
        if not record.exists(): return
        helper=Path(__file__).with_name('hermes_cleanup.py')
        python=Path(binary).parent/'python'
        if not python.is_file(): raise ToolInfrastructureError('Cannot clean Hermes owner: interpreter missing')
        cleanup=subprocess.run([str(python),str(helper),str(self.home)],env=env,capture_output=True,text=True,timeout=15)
        if cleanup.returncode: raise ToolInfrastructureError('Hermes owner cleanup failed; inspect local cleanup log')

    def session_environment(self):
        # These are independent headless researchers, not user-facing gateway
        # profiles. Sharing the upstream host singleton joins unrelated jobs or
        # rejects a legitimate parallel worker before any model call.
        return {'PATH':os.environ.get('PATH','/usr/bin:/bin'),
                'HERMES_HOME':str(self.home),
                'HERMES_GATEWAY_LOCK_DIR':str(self.home/'gateway-locks'),
                'PYTHONDONTWRITEBYTECODE':'1'}

    def run(self, prompt, tools, workspace, budget) -> TransportResult:
        self.provider['session_seconds']=float(budget['session_seconds'])
        self.tool_names=sorted(tools)
        self._home_written=False
        checks=self.preflight()
        failures=[check for check in checks if not check.get('ok')]
        if failures:raise ToolInfrastructureError('Hermes preflight failed: '+json.dumps(failures))
        binary = self.resolve_binary()
        sessions = self.job_dir / 'private' / 'hermes-sessions'
        sessions.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime('%Y%m%dT%H%M%S')
        prompt_path = sessions / f'prompt-{stamp}.txt'
        prompt_path.write_text(prompt)
        prompt_path.chmod(0o600)
        usage_path = sessions / f'usage-{stamp}.json'
        stream_path = sessions / f'stream-{stamp}.jsonl'
        model = self.provider.get('requested_model')
        command = [binary, '--usage-file', str(usage_path), 'chat', '--oneshot', '--quiet',
                   '--format', 'stream-json',
                   '--max-turns', '0',  # Upstream's explicit unlimited mode; host timer owns checkpoints.
                   '--query-file', str(prompt_path),
                   '--provider', f'custom:{self.provider_name}',
                   '--ignore-rules', '--toolsets', 'seeder', '--in', str(self.job_dir / 'worker')]
        if model:
            command += ['-m', model]
        env = self.session_environment()
        result = TransportResult()
        started = time.monotonic()
        timeout = max(1.0, float(budget.get('session_seconds', 3600)))
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env, cwd=str(self.job_dir / 'worker'),
            start_new_session=True)   # own group: a timeout must take down MCP children too
        checkpoint=False
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            process.wait()
            result.model_seconds = time.monotonic() - started
            self._stop_owner(binary,env)
            stdout,stderr=process.communicate(timeout=5)
            exit_code=0
            checkpoint=True
        except KeyboardInterrupt:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            process.wait()
            result.model_seconds = time.monotonic() - started
            self._stop_owner(binary,env)
            raise
        self._stop_owner(binary,env)
        result.model_seconds = time.monotonic() - started
        stream_path.write_text(stdout or '')
        if usage_path.is_file():
            try:
                result.usage = json.loads(usage_path.read_text())
            except ValueError:
                result.usage = {'raw': usage_path.read_text()[:4000]}
        self._absorb_stream(stdout or '', result)
        reason=str(result.usage.get('turn_exit_reason',''))
        turn_checkpoint=(exit_code == 1 and result.usage.get('failed') is False
                         and reason.startswith('max_iterations_reached('))
        if turn_checkpoint:
            checkpoint=True
            exit_code=0
            result.usage['checkpoint_reason']=reason
        if exit_code != 0 or result.usage.get('failed'):
            detail = provider_error_detail(stdout, stderr)
            result.error_detail = detail
            result.finished_reason = 'error'
            classified = classify_provider_error(detail)
            if classified is not None:
                result.error_class = 'rate_limit' \
                    if isinstance(classified, ProviderRateLimit) else 'refused'
                raise classified
            raise RuntimeError('Hermes CLI failed with exit code '
                               f'{exit_code}: {detail[:2000]}')
        if checkpoint:
            result.usage.setdefault('cost_status','unknown')
            result.usage['interrupted']=True
            result.error_detail='Session checkpoint reached; own drafts and experiment ledger preserved'
        if isinstance(result.usage,dict):
            result.session_id=result.usage.get('session_id','')
        result.finished_reason = 'done'
        return result

    def _absorb_stream(self, stream_text, result) -> None:
        """Record served models / final text from --format stream-json output.

        Hermes emits one JSON object per line. Any `model` field seen on an
        event is recorded as a served model — the same observed-vs-requested
        honesty as the Claude backend, with no assumption about event shapes.
        """
        last_text = ''
        for line in stream_text.splitlines():
            line = line.strip()
            if not line.startswith('{'):
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            model = event.get('model')
            if isinstance(model, str) and model:
                result.served_model = model
                if model not in self.served_models:
                    self.served_models.append(model)
            for key in ('text', 'content', 'result', 'response'):
                value = event.get(key)
                if isinstance(value, str) and value.strip():
                    last_text = value
        if not result.usage.get('session_text') and last_text:
            result.usage['session_text'] = last_text[:2000]
