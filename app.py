from __future__ import annotations
import json, os, re, secrets, subprocess, time, urllib.request, urllib.error
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

APP_NAME = "ARKI Bridge"
ROOTS = {
    "sicl-web": Path(os.getenv("ARKI_SICL_WEB", "/home/arki/ARKI/canonical/sicl-web")).resolve(),
    "sicl-core": Path(os.getenv("ARKI_SICL_CORE", "/home/arki/ARKI/canonical/sicl-core")).resolve(),
}
TOKEN = os.getenv("ARKI_BRIDGE_TOKEN", "")
MAX_READ_BYTES = int(os.getenv("ARKI_BRIDGE_MAX_READ_BYTES", "200000"))
AUDIT_LOG = Path(os.getenv("ARKI_BRIDGE_AUDIT_LOG", "/var/log/arki-bridge/audit.jsonl"))

# ARKI Identity (F3): introspección loopback al endpoint interno de SICL Web.
SICL_WEB_BASE = os.getenv("SICL_WEB_BASE", "http://127.0.0.1:8000").rstrip("/")
IDENTITY_INTERNAL_KEY = os.getenv("ARKI_IDENTITY_INTERNAL_KEY", "")
IDENTITY_TIMEOUT = float(os.getenv("ARKI_IDENTITY_TIMEOUT", "3.0"))
IDENTITY_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")

app = FastAPI(title=APP_NAME, version="0.2.0")

def audit(action: str, repo: str | None, outcome: str, detail: str = ""):
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time()), "action": action, "repo": repo,
                               "outcome": outcome, "detail": detail[:500]}, ensure_ascii=False) + "\n")
    except Exception:
        pass

def verify_arki_token(token: str) -> dict | None:
    """Verifica un token opaco de ARKI Identity vía introspección loopback.
    Retorna {subject, client_id, scopes} si válido, None si inválido/no aplicable.
    Nunca loguea el token."""
    if not IDENTITY_INTERNAL_KEY:
        return None
    if not IDENTITY_TOKEN_RE.fullmatch(token or ""):
        return None
    payload = json.dumps({"token": token}).encode("utf-8")
    req = urllib.request.Request(
        f"{SICL_WEB_BASE}/api/internal/identity/introspect",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Internal-Key": IDENTITY_INTERNAL_KEY,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=IDENTITY_TIMEOUT) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("valid"):
        return None
    scopes = data.get("scopes") or []
    if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
        return None
    return {
        "subject": data.get("subject"),
        "client_id": data.get("client_id"),
        "scopes": scopes,
    }

def authorize(authorization: str | None) -> dict:
    """Doble camino: token estático (compat) o token ARKI Identity (F3).
    Devuelve dict con {subject, client_id, scopes} para uso futuro (F4).
    No enforcea scopes aún (F4 lo activará en cada endpoint)."""
    if not TOKEN and not IDENTITY_INTERNAL_KEY:
        raise HTTPException(503, "Bridge authentication not configured")
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not supplied:
        raise HTTPException(401, "Unauthorized")
    # Camino 1: token estático (compat total)
    if TOKEN and secrets.compare_digest(supplied, TOKEN):
        return {"subject": "bridge-static", "client_id": "bridge-local", "scopes": ["*"]}
    # Camino 2: token ARKI Identity (introspección loopback)
    identity = verify_arki_token(supplied)
    if identity is not None:
        return identity
    raise HTTPException(401, "Unauthorized")

def repo_path(repo: str) -> Path:
    if repo not in ROOTS:
        raise HTTPException(404, "Unknown repository")
    p = ROOTS[repo]
    if not p.is_dir() or not (p / ".git").exists():
        raise HTTPException(503, f"Repository unavailable: {repo}")
    return p

def run_fixed(repo: str, args: list[str], timeout: int = 20):
    root = repo_path(repo)
    try:
        p = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, "GIT_TERMINAL_PROMPT":"0"})
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Operation timed out")
    output = (p.stdout + ("\n" + p.stderr if p.stderr else "")).strip()
    audit("command", repo, "ok" if p.returncode == 0 else "failed", " ".join(args))
    return {"repo": repo, "exit_code": p.returncode, "output": output[:30000]}

@app.middleware("http")
async def no_cache(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

@app.get("/health")
def health():
    return {"service":"arki-bridge","version":"0.2.0","auth":"required for operations",
            "identity_configured": bool(IDENTITY_INTERNAL_KEY)}

@app.get("/v1/status")
def status(authorization: str | None = Header(default=None)):
    authorize(authorization)
    result = {}
    for name, root in ROOTS.items():
        if root.is_dir() and (root / ".git").exists():
            result[name] = run_fixed(name, ["git","status","--short","--branch"])
        else:
            result[name] = {"available":False,"path":str(root)}
    audit("status", None, "ok")
    return result

@app.get("/v1/git/{repo}/status")
def git_status(repo: str, authorization: str | None = Header(default=None)):
    authorize(authorization)
    return run_fixed(repo, ["git","status","--short","--branch"])

@app.get("/v1/git/{repo}/branch")
def git_branch(repo: str, authorization: str | None = Header(default=None)):
    authorize(authorization)
    return run_fixed(repo, ["git","branch","--show-current"])

@app.get("/v1/git/{repo}/head")
def git_head(repo: str, authorization: str | None = Header(default=None)):
    authorize(authorization)
    return run_fixed(repo, ["git","rev-parse","HEAD"])

@app.get("/v1/git/{repo}/diff")
def git_diff(repo: str, staged: bool = False, authorization: str | None = Header(default=None)):
    authorize(authorization)
    args = ["git","diff","--no-ext-diff","--no-color"]
    if staged: args.append("--cached")
    args.append("--")
    return run_fixed(repo, args, timeout=30)

class ReadRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)

@app.post("/v1/files/{repo}/read")
def read_file(repo: str, body: ReadRequest, authorization: str | None = Header(default=None)):
    authorize(authorization)
    root = repo_path(repo)
    rel = Path(body.path)
    if rel.is_absolute() or any(part in ("..", "") for part in rel.parts):
        raise HTTPException(400, "Invalid relative path")
    allowed_ext = {".py",".ts",".tsx",".js",".json",".md",".txt",".yml",".yaml",".toml",".sql",".sh",".env.example"}
    if rel.suffix.lower() not in allowed_ext:
        raise HTTPException(403, "File extension not allowed")
    target = (root / rel).resolve()
    if root not in target.parents:
        raise HTTPException(403, "Path escapes repository")
    if not target.is_file():
        raise HTTPException(404, "File not found")
    size = target.stat().st_size
    if size > MAX_READ_BYTES:
        raise HTTPException(413, f"File too large ({size} bytes)")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(415, "Not UTF-8 text")
    audit("read_file", repo, "ok", str(rel))
    return {"repo":repo,"path":str(rel),"bytes":size,"content":content}

class TestRequest(BaseModel):
    suite: Literal["core-pytest", "web-vitest"] = "core-pytest"

@app.post("/v1/test")
def run_test(body: TestRequest, authorization: str | None = Header(default=None)):
    authorize(authorization)
    if body.suite == "core-pytest":
        repo = "sicl-core"
        args = ["python3","-m","pytest","-q"]
    elif body.suite == "web-vitest":
        repo = "sicl-web"
        args = ["pnpm","test","--","--run"]
    else:
        raise HTTPException(400, "Unknown suite")
    return run_fixed(repo, args, timeout=240)

@app.get("/v1/services")
def services(authorization: str | None = Header(default=None)):
    authorize(authorization)
    names = ["sicl-core.service","sicl-web.service","arki-arbol-vivo.service","arki-maqueta-viva.service"]
    out = []
    for name in names:
        p = subprocess.run(["systemctl","is-active",name],capture_output=True,text=True,timeout=10)
        out.append({"unit":name,"state":p.stdout.strip() or p.stderr.strip()})
    audit("services",None,"ok")
    return {"services":out}

@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    audit("error",None,"error",type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail":"Internal bridge error"})
