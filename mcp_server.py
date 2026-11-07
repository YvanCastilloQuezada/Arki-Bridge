"""ARKI Bridge — servidor MCP (F6.5).
Expone las operaciones del Bridge como herramientas MCP para ChatGPT.

IMPORTANTE: ChatGPT Go NO soporta MCP personalizado. Este módulo queda
listo para cuando el usuario suba a ChatGPT Pro o Business.
"""
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
import json

# Importar la app FastAPI existente para reutilizar authorize/require_scope
# y las funciones de negocio.
import app as bridge_app

mcp = FastMCP("ARKI Bridge")

# Helper para convertir errores del Bridge a respuestas MCP legibles.
def _handle(fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        # Si el Bridge devolvió un dict con "detail" de error, propagarlo.
        if isinstance(result, dict) and "detail" in result and isinstance(result["detail"], str):
            return {"error": result["detail"]}
        return result
    except bridge_app.HTTPException as e:
        return {"error": f"HTTP {e.status_code}: {e.detail}"}
    except Exception as e:
        return {"error": str(e)}

# --- Herramientas MCP (1:1 con los endpoints REST) ---
# Todas son read-only: usan ToolAnnotations(readOnlyHint=True) para que
# ChatGPT no pida confirmación antes de cada llamada.

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_bridge_health() -> dict:
    """Estado del Bridge. No requiere autenticación."""
    return {"service": "arki-bridge", "version": "0.2.0", "status": "ok"}

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_repo_status(token: str) -> dict:
    """Estado de los repositorios sicl-web y sicl-core (git status).
    Requiere token ARKI con scope git:read."""
    identity = bridge_app.authorize(f"Bearer {token}")
    bridge_app.require_scope(identity, "git:read")
    result = {}
    for name, root in bridge_app.ROOTS.items():
        if root.is_dir() and (root / ".git").exists():
            result[name] = _handle(bridge_app.run_fixed, name, ["git", "status", "--short", "--branch"])
        else:
            result[name] = {"available": False}
    return result

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_git_status(repo: str, token: str) -> dict:
    """git status de un repo. repo: 'sicl-web' o 'sicl-core'.
    Requiere token ARKI con scope git:read."""
    identity = bridge_app.authorize(f"Bearer {token}")
    bridge_app.require_scope(identity, "git:read")
    return _handle(bridge_app.run_fixed, repo, ["git", "status", "--short", "--branch"])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_git_branch(repo: str, token: str) -> dict:
    """Rama actual de un repo. Requiere token ARKI con scope git:read."""
    identity = bridge_app.authorize(f"Bearer {token}")
    bridge_app.require_scope(identity, "git:read")
    return _handle(bridge_app.run_fixed, repo, ["git", "branch", "--show-current"])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_git_head(repo: str, token: str) -> dict:
    """Commit HEAD de un repo. Requiere token ARKI con scope git:read."""
    identity = bridge_app.authorize(f"Bearer {token}")
    bridge_app.require_scope(identity, "git:read")
    return _handle(bridge_app.run_fixed, repo, ["git", "rev-parse", "HEAD"])

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_git_diff(repo: str, staged: bool, token: str) -> dict:
    """Diff de un repo. staged: true para diff staged.
    Requiere token ARKI con scope git:read."""
    identity = bridge_app.authorize(f"Bearer {token}")
    bridge_app.require_scope(identity, "git:read")
    args = ["git", "diff", "--no-ext-diff", "--no-color"]
    if staged:
        args.append("--cached")
    args.append("--")
    return _handle(bridge_app.run_fixed, repo, args, 30)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def read_repo_file(repo: str, path: str, token: str) -> dict:
    """Leer un archivo rastreado. path es relativo al repo.
    Requiere token ARKI con scope files:read."""
    identity = bridge_app.authorize(f"Bearer {token}")
    bridge_app.require_scope(identity, "files:read")
    # Reutilizar la lógica del endpoint REST directamente
    try:
        from pathlib import Path
        root = bridge_app.repo_path(repo)
        rel = Path(path)
        if rel.is_absolute() or any(part in ("..", "") for part in rel.parts):
            return {"error": "Invalid relative path"}
        target = (root / rel).resolve()
        if root not in target.parents:
            return {"error": "Path escapes repository"}
        if not target.is_file():
            return {"error": "File not found"}
        if target.stat().st_size > bridge_app.MAX_READ_BYTES:
            return {"error": "File too large"}
        return {"repo": repo, "path": str(rel), "content": target.read_text(encoding="utf-8")}
    except Exception as e:
        return {"error": str(e)}

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

# Punto de entrada para uvicorn (se monta en app.py)
mcp_app = mcp.http_app()
