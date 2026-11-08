"""ARKI Bridge — entrypoint MCP en puerto separado.
Corre como app uvicorn independiente en :18770.
Reutiliza las funciones del Bridge REST (authorize, require_scope, run_fixed).
"""
from __future__ import annotations
import sys
sys.path.insert(0, "/opt/arki-bridge")

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

# Importar la app del Bridge para reutilizar authorize/require_scope/run_fixed
import app as bridge_app

mcp = FastMCP("ARKI Bridge")

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_bridge_health() -> dict:
    """Estado del Bridge. No requiere autenticación."""
    return {"service": "arki-bridge", "version": "0.2.0", "status": "ok"}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_repo_status(token: str) -> dict:
    """Estado de sicl-web y sicl-core (git status).
    Requiere token ARKI con scope git:read."""
    identity = bridge_app.authorize(f"Bearer {token}")
    bridge_app.require_scope(identity, "git:read")
    result = {}
    for name, root in bridge_app.ROOTS.items():
        if root.is_dir() and (root / ".git").exists():
            result[name] = bridge_app.run_fixed(name, ["git", "status", "--short", "--branch"])
        else:
            result[name] = {"available": False}
    return result

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_git_status(repo: str, token: str) -> dict:
    """git status de un repo. repo: 'sicl-web' o 'sicl-core'.
    Requiere token ARKI con scope git:read."""
    identity = bridge_app.authorize(f"Bearer {token}")
    bridge_app.require_scope(identity, "git:read")
    return bridge_app.run_fixed(repo, ["git", "status", "--short", "--branch"])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_git_branch(repo: str, token: str) -> dict:
    """Rama actual de un repo. Requiere token ARKI con scope git:read."""
    identity = bridge_app.authorize(f"Bearer {token}")
    bridge_app.require_scope(identity, "git:read")
    return bridge_app.run_fixed(repo, ["git", "branch", "--show-current"])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_git_head(repo: str, token: str) -> dict:
    """Commit HEAD de un repo. Requiere token ARKI con scope git:read."""
    identity = bridge_app.authorize(f"Bearer {token}")
    bridge_app.require_scope(identity, "git:read")
    return bridge_app.run_fixed(repo, ["git", "rev-parse", "HEAD"])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_services_status(token: str) -> dict:
    """Estado de servicios systemd. Requiere token ARKI con scope services:read."""
    identity = bridge_app.authorize(f"Bearer {token}")
    bridge_app.require_scope(identity, "services:read")
    import subprocess
    names = ["sicl-core.service", "sicl-web.service", "arki-arbol-vivo.service", "arki-maqueta-viva.service"]
    out = []
    for name in names:
        p = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=10)
        out.append({"unit": name, "state": p.stdout.strip() or p.stderr.strip()})
    return {"services": out}

# App raíz — MCP es la app, no sub-app
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_git_diff(repo: str, token: str, staged: bool = False) -> dict:
    """Diff de un repositorio.
    repo: 'sicl-web' o 'sicl-core'.
    staged=True muestra cambios preparados.
    Requiere token ARKI con scope git:read."""
    identity = bridge_app.authorize(f"Bearer {token}")
    bridge_app.require_scope(identity, "git:read")
    args = ["git", "diff", "--no-ext-diff", "--no-color"]
    if staged:
        args.append("--cached")
    args.append("--")
    return bridge_app.run_fixed(repo, args, timeout=30)

# ARKI_MCP_43_TOOLS_BEGIN
# ARKI BRIDGE — 43 herramientas MCP adicionales, solo lectura.

from mcp.types import ToolAnnotations


def _arki_read_tool(repo: str, token: str, git_args: list[str]) -> dict:
    identity = bridge_app.authorize(f"Bearer {token}")
    bridge_app.require_scope(identity, "git:read")

    return bridge_app.run_fixed(
        repo,
        ["git"] + git_args,
        timeout=30,
    )


def _register_arki_read_tool(name: str, git_args: list[str]) -> None:
    def tool(repo: str, token: str) -> dict:
        return _arki_read_tool(repo, token, git_args)

    tool.__name__ = name
    tool.__qualname__ = name

    mcp.tool(
        name=name,
        annotations=ToolAnnotations(readOnlyHint=True),
    )(tool)


_ARKI_43_TOOLS = [
    ('get_git_log', ['log', '-n', '20', '--format=%H %an %ad %s', '--date=short']),
    ('get_git_log_oneline', ['log', '-n', '30', '--oneline']),
    ('get_git_log_graph', ['log', '-n', '30', '--graph', '--oneline', '--decorate']),
    ('get_git_log_author', ['log', '-n', '30', '--format=%an <%ae>']),
    ('get_git_log_dates', ['log', '-n', '30', '--format=%H %ad', '--date=iso']),
    ('get_git_last_commit', ['log', '-1', '--format=%H%n%an%n%ae%n%ad%n%s', '--date=iso']),
    ('get_git_commit_stats', ['log', '-1', '--stat']),
    ('get_git_commit_files', ['diff-tree', '--no-commit-id', '--name-status', '-r', 'HEAD']),
    ('get_git_commit_summary', ['show', '-s', '--format=fuller', 'HEAD']),
    ('get_git_commit_count', ['rev-list', '--count', 'HEAD']),
    ('get_git_branches', ['branch']),
    ('get_git_branches_all', ['branch', '-a']),
    ('get_git_branch_verbose', ['branch', '-vv']),
    ('get_git_branch_merged', ['branch', '--merged']),
    ('get_git_branch_unmerged', ['branch', '--no-merged']),
    ('get_git_tags', ['tag', '--list']),
    ('get_git_tags_latest', ['tag', '--sort=-creatordate']),
    ('get_git_refs', ['show-ref']),
    ('get_git_remote', ['remote', '-v']),
    ('get_git_tracking_branch', ['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}']),
    ('get_git_changed_files', ['diff', '--name-only']),
    ('get_git_changed_names', ['diff', '--name-status']),
    ('get_git_diff_stat', ['diff', '--stat']),
    ('get_git_diff_names', ['diff', '--name-only', 'HEAD']),
    ('get_git_diff_cached', ['diff', '--cached']),
    ('get_git_diff_cached_stat', ['diff', '--cached', '--stat']),
    ('get_git_status_porcelain', ['status', '--porcelain=v1']),
    ('get_git_untracked', ['ls-files', '--others', '--exclude-standard']),
    ('get_git_staged', ['diff', '--cached', '--name-status']),
    ('get_git_conflicts', ['diff', '--name-only', '--diff-filter=U']),
    ('get_repo_root', ['rev-parse', '--show-toplevel']),
    ('get_repo_git_dir', ['rev-parse', '--absolute-git-dir']),
    ('get_repo_object_format', ['rev-parse', '--show-object-format']),
    ('get_repo_shallow', ['rev-parse', '--is-shallow-repository']),
    ('get_repo_tree', ['ls-tree', '-r', '--name-only', 'HEAD']),
    ('get_repo_tree_root', ['ls-tree', '--name-only', 'HEAD']),
    ('get_repo_files', ['ls-files']),
    ('get_repo_readme', ['ls-files', '--', '*README*']),
    ('get_repo_docs', ['ls-files', '--', '*.md']),
    ('get_repo_submodules', ['submodule', 'status']),
    ('get_repo_tracked_directories', ['ls-tree', '-d', '--name-only', 'HEAD']),
    ('get_repo_recent_files', ['log', '-n', '20', '--name-only', '--format=']),
    ('get_repo_contributors', ['shortlog', '-n', '-s', 'HEAD']),

]

if len(_ARKI_43_TOOLS) != 43:
    raise RuntimeError("El registro MCP no contiene 43 herramientas.")

for _name, _args in _ARKI_43_TOOLS:
    _register_arki_read_tool(_name, _args)

# ARKI_MCP_43_TOOLS_END

app = mcp.http_app(path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=18770, log_level="info")
