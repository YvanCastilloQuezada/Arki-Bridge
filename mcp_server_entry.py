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
app = mcp.http_app(path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=18770, log_level="info")
