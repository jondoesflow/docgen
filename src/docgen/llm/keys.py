"""API-key resolution and storage for the LLM tier.

Resolution precedence at runtime (first hit wins), reported honestly by
`docgen model status`:

1. the provider's real environment variable (e.g. ANTHROPIC_API_KEY)
2. the OS keyring (Credential Manager / Keychain / Secret Service)
3. a git-ignored .env file in the project directory (0600), the fallback for
   headless/CI machines where no keyring backend is available

A CLI process cannot persistently set an environment variable in its parent
shell, which is why `docgen model key` writes to the keyring (or .env) instead.
Keys never appear in config YAML, logs, error messages, or command output —
display always goes through mask_key()."""

from __future__ import annotations

import contextlib
import os
import stat
import sys
from pathlib import Path

from docgen.llm.registry import ProviderSpec

KEYRING_SERVICE = "docgen"
ENV_FILE = ".env"


def mask_key(value: str) -> str:
    """Show only the last 4 characters; never enough to reconstruct the key."""
    if len(value) < 8:
        return "****"
    return "****" + value[-4:]


def resolve_api_key(spec: ProviderSpec, env_dir: Path | None = None) -> tuple[str, str] | None:
    """Return (key, human-readable source) for a provider, or None."""
    value = os.environ.get(spec.env_var)
    if value:
        return value, f"environment variable {spec.env_var}"
    value = _keyring_get(spec)
    if value:
        return value, "OS keyring"
    value = read_env_file(env_dir or Path.cwd()).get(spec.env_var)
    if value:
        return value, f"{ENV_FILE} file"
    return None


# Keyring failures must never break docgen: a missing backend, a locked
# store, or a broken native dependency (some backends crash with
# non-Exception errors, e.g. pyo3 PanicException, and print panics straight
# to fd 2) all just mean "keyring unavailable" — fall through to the next
# source, silently, and only probe a broken backend once per process.

_keyring_unavailable = False


@contextlib.contextmanager
def _quiet_stderr():
    """Silence stderr at the fd level while probing the keyring — broken
    native backends write panic output directly to fd 2, bypassing Python."""
    try:
        stderr_fd = sys.stderr.fileno()
    except Exception:  # stderr replaced (e.g. under pytest capture) — nothing to silence
        yield
        return
    saved = os.dup(stderr_fd)
    try:
        with open(os.devnull, "wb") as devnull:
            os.dup2(devnull.fileno(), stderr_fd)
        yield
    finally:
        os.dup2(saved, stderr_fd)
        os.close(saved)


def _keyring_get(spec: ProviderSpec) -> str | None:
    global _keyring_unavailable
    if _keyring_unavailable:
        return None
    try:
        import keyring

        with _quiet_stderr():
            return keyring.get_password(KEYRING_SERVICE, spec.key)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        _keyring_unavailable = True
        return None


def store_key_in_keyring(spec: ProviderSpec, value: str) -> bool:
    """Store in the OS keyring; False when no usable backend is available."""
    global _keyring_unavailable
    if _keyring_unavailable:
        return False
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring

        with _quiet_stderr():
            if isinstance(keyring.get_keyring(), FailKeyring):
                return False
            keyring.set_password(KEYRING_SERVICE, spec.key, value)
            return keyring.get_password(KEYRING_SERVICE, spec.key) == value
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        _keyring_unavailable = True
        return False


def delete_key_from_keyring(spec: ProviderSpec) -> None:
    try:
        import keyring

        with _quiet_stderr():
            keyring.delete_password(KEYRING_SERVICE, spec.key)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        pass


def read_env_file(directory: Path) -> dict[str, str]:
    """Minimal KEY=value parser (comments and blank lines ignored)."""
    path = Path(directory) / ENV_FILE
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def store_key_in_env_file(spec: ProviderSpec, value: str, directory: Path | None = None) -> Path:
    """Write/update the provider's key in .env (0600) and git-ignore it."""
    directory = Path(directory or Path.cwd())
    path = directory / ENV_FILE
    lines: list[str] = []
    replaced = False
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.split("=", 1)[0].strip() == spec.env_var:
                lines.append(f"{spec.env_var}={value}")
                replaced = True
            else:
                lines.append(line)
    if not replaced:
        lines.append(f"{spec.env_var}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    _ensure_gitignored(directory)
    return path


def _ensure_gitignored(directory: Path) -> None:
    gitignore = directory / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    entries = {line.strip() for line in existing.splitlines()}
    if ENV_FILE in entries or f"/{ENV_FILE}" in entries:
        return
    prefix = existing if not existing or existing.endswith("\n") else existing + "\n"
    gitignore.write_text(prefix + ENV_FILE + "\n", encoding="utf-8", newline="\n")
