# Local Development Setup

Personal mirror checklist for running this fork on a fresh machine (WSL Ubuntu, another macOS box, or anywhere else). The upstream `README.md` covers the project itself; this file documents the gitignored files that need to be recreated and the global Python toolchain assumptions baked into the workflow.

## Files that don't ship in git

The following are intentionally gitignored. Recreate each before running anything.

- `.env`. Real API keys. `cp .env.example .env` and fill in values.
- `.envrc`. Per-project direnv hook. `cp .envrc.example .envrc` then `direnv allow`. Optional if you use the global zsh `_venv_auto_activate` hook described below.
- `.venv/`. Rebuilt by `uv sync` from `uv.lock`. Never tracked.
- `reports/`. Run output written by the agents at runtime.

`.env.enterprise.example` is also tracked for users wiring up enterprise providers.

## One-time machine setup

1. Install `uv`:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   `uv` installs to `~/.local/bin`. The shell adds that directory to PATH via `~/.zshenv` (zsh) or `~/.bashrc` (bash); the line is `export PATH="$HOME/.local/bin:$PATH"`.

2. Install `direnv` if you want per-project hooks beyond the venv:
   ```bash
   sudo apt install direnv     # Ubuntu / WSL
   brew install direnv          # macOS
   ```

3. Install Ollama (only needed for the local-LLM path used in `main.py`):
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ```

## Per-project setup (this repo)

```bash
git clone git@github.com:av1155/TradingAgents.git
cd TradingAgents
cp .env.example .env              # fill in keys
cp .envrc.example .envrc          # only if using direnv
direnv allow                      # only if using direnv
uv sync                           # creates .venv/ from uv.lock
```

`uv` reads `pyproject.toml` (`requires-python = ">=3.10"`) and downloads a matching CPython if the system doesn't have one. To pin the same Python the macOS box uses (`3.13.5`), run `uv python pin 3.13` once. That writes a `.python-version` file you can either commit or leave local.

Run with `uv run python main.py`, or, if the zsh hook below is active, just `python main.py` (the venv is already on PATH).

## Global Python toolchain

`uv` is the only Python manager on this account. No pyenv, no system pip, no conda.

- Interpreter installs: `uv python install 3.13`
- Project setup: `uv sync` (reads `pyproject.toml` + `uv.lock`)
- Adding a dep: `uv add <pkg>` (mutates `pyproject.toml`, regenerates lockfile)
- One-off scripts: `uv run python script.py` (auto-syncs first)
- Global CLIs (ruff, mypy, etc.): `uv tool install <name>`. Never `pip install --user`.
- Lockfile policy: `uv.lock` is committed. `requirements.txt` is generated on demand via `uv export` only when a tool demands pip-style input.

Current macOS interpreter inventory (`uv python list --only-installed`):

```
cpython-3.14.4   homebrew  (system 3.14)
cpython-3.13.13  homebrew  (system 3.13)
cpython-3.13.5   uv-managed  (active .venv for this project)
cpython-3.12.11  uv-managed
cpython-3.9.6    /usr/bin (Apple stub, ignored)
```

## How `.zshrc` activates venvs

Two zsh hooks plus direnv handle activation. All three pieces live in `~/.dotfiles/ZSH/.zshrc`.

`_venv_auto_activate` (around line 197) walks from `$PWD` toward `/`, finds the nearest `.venv/`, and prepends `.venv/bin` to PATH without sourcing the venv's `activate` script. That keeps PS1 untouched; the Pure prompt reads `VIRTUAL_ENV_PROMPT` directly and renders `.venv` consistently.

```zsh
_venv_auto_activate() {
    local d=$PWD
    while [ "$d" != "/" ]; do
        if [ -x "$d/.venv/bin/python" ]; then
            if [ "$VIRTUAL_ENV" != "$d/.venv" ]; then
                if [ -z "${_VENV_PATH_BACKUP:-}" ]; then
                    export _VENV_PATH_BACKUP="$PATH"
                fi
                export VIRTUAL_ENV="$d/.venv"
                export VIRTUAL_ENV_PROMPT=".venv"
                export PATH="$VIRTUAL_ENV/bin:$_VENV_PATH_BACKUP"
            fi
            return
        fi
        d=${d:h}
    done
    # leaving every venv: restore PATH and clear markers
    if [ -n "${VIRTUAL_ENV:-}" ]; then
        if [ -n "${_VENV_PATH_BACKUP:-}" ]; then
            export PATH="$_VENV_PATH_BACKUP"
            unset _VENV_PATH_BACKUP
        fi
        unset VIRTUAL_ENV VIRTUAL_ENV_PROMPT
    fi
}
autoload -U add-zsh-hook
add-zsh-hook chpwd _venv_auto_activate
```

`_venv_sync_prompt` (around line 230) keeps the indicator literal across direnv resets that happen between `.envrc` transitions:

```zsh
_venv_sync_prompt() {
    if [ -n "${VIRTUAL_ENV:-}" ] && [ "${VIRTUAL_ENV_PROMPT:-}" != ".venv" ]; then
        export VIRTUAL_ENV_PROMPT=".venv"
    fi
}
add-zsh-hook precmd _venv_sync_prompt
```

direnv is loaded earlier in the file:

```zsh
if command -v direnv &>/dev/null; then
    eval "$(direnv hook zsh)"
fi
```

The very bottom of `.zshrc` calls the activator once explicitly, so a shell that starts inside a project directory captures the full final PATH (including all the `path+=` mutations from `.zprofile`):

```zsh
# Must run after every PATH mutation above so _VENV_PATH_BACKUP captures the full PATH.
_venv_auto_activate
```

Net effect: `cd` into any directory whose tree contains a `.venv/` and you get the right Python on PATH automatically. Leaving the tree restores the original PATH. The Pure prompt always shows `.venv` as the indicator while inside a project, blank outside.

## Mirroring on WSL Ubuntu

Same toolchain, with `apt` instead of `brew` and the Linux installer for `uv`.

```bash
sudo apt update && sudo apt install -y zsh direnv git curl build-essential
chsh -s "$(which zsh)"
curl -LsSf https://astral.sh/uv/install.sh | sh
```

If you GNU-stow `~/.dotfiles/ZSH/` on the Ubuntu side, both hooks work unchanged. The activator uses zsh-specific `${d:h}` parameter expansion, but the file is sourced by zsh so that's fine. `.zprofile` already branches on `uname -s` and skips the macOS Homebrew block on Linux.

If you stay on bash without stowing the dotfiles, direnv alone covers activation. Append the hook to `~/.bashrc` once:

```bash
# direnv: auto-load .envrc on cd (replaces zsh's _venv_auto_activate)
command -v direnv >/dev/null && eval "$(direnv hook bash)"
```

Stock Ubuntu's bash does not put `~/.local/bin` on PATH for non-login shells, so also add `export PATH="$HOME/.local/bin:$PATH"` if it isn't already in `~/.bashrc`. The `.envrc.example` snippet is POSIX and loads unchanged in both shells. The two zsh hooks (`_venv_auto_activate`, `_venv_sync_prompt`) have no bash port because direnv loading `.envrc` already handles the activation work the project relies on. Apt's direnv on Ubuntu noble is `2.32.1`; the hook protocol matches upstream `2.37.x`, so the same `.envrc` loads either version.

Local Ollama config goes in `.envrc` via `TRADINGAGENTS_LLM_PROVIDER`, `TRADINGAGENTS_LLM_BACKEND_URL`, `TRADINGAGENTS_DEEP_THINK_LLM`, `TRADINGAGENTS_QUICK_THINK_LLM` (template in `.envrc.example`). `DEFAULT_CONFIG` applies them on import; `main.py` stays unmodified.

- If Ollama runs inside WSL2, `http://127.0.0.1:11434/v1` works as-is.
- If Ollama runs on the Windows host, swap `127.0.0.1` for `awk '/nameserver/ {print $2}' /etc/resolv.conf`.
- Pull the model named in `TRADINGAGENTS_DEEP_THINK_LLM` (e.g. `qwen3.6-27b-agent`) before running.

## Quick sanity check after setup

```bash
uv run python -c "import sys, langgraph, langchain_openai; print(sys.version)"
uv run python main.py        # full agent run, requires Ollama or a configured remote provider
uv run pytest -q             # full test suite (some integration tests need API keys)
```

## Pulling upstream updates

`main` is a pure mirror of `TauricResearch/TradingAgents:main`. Customizations live on `local-setup`. To absorb upstream commits:

```bash
git fetch upstream
git checkout main && git merge --ff-only upstream/main && git push origin main
git checkout local-setup && git rebase upstream/main && git push --force-with-lease origin local-setup
```

`main` must fast-forward — if it doesn't, something got committed there by mistake; reset it back to `upstream/main` instead. Rebase conflicts on `local-setup` pinpoint customizations upstream has obsoleted.
