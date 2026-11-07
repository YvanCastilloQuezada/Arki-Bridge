from __future__ import annotations
import os, secrets, subprocess, time
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

app = FastAPI(title=APP_NAME, version="0.1.0")

def audit(action: str, repo: str | None, outcome: str, detail: str = ""):
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        import json
        with AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time()), "action": action, "repo": repo,
                               "outcome": outcome, "detail": detail[:500]}, ensure_ascii=False) + "\n")
    except Exception:
        pass

def authorize(authorization: str | None):
    if not TOKEN:
        raise HTTPException(503, "Bridge token not configured")
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not supplied or not secrets.compare_digest(supplied, TOKEN):
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
    return {"service":"arki-bridge","version":"0.1.0","auth":"required for operations"}

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
    # Restrict reads to tracked files and common project text/config formats.
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
    # Exact allowlist; no user-provided shell or args.
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
    # Fixed list only. systemctl is invoked without shell.
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
