#!/usr/bin/env python3
"""ARKI MCP — 50 pruebas, 1 por tool.
Ejecuta como arki-bridge con grupo arki (1000) para leer /home/arki.
Carga bridge.env antes de importar app (app.py lee ARKI_SICL_WEB al importar).
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Validar variables inyectadas por el proceso padre.
#    Este script NO lee bridge.env: es un archivo protegido.
# ---------------------------------------------------------------------------
if not os.environ.get("ARKI_BRIDGE_TOKEN"):
    print("ERROR: ARKI_BRIDGE_TOKEN no disponible en entorno")
    sys.exit(2)

if not os.environ.get("ARKI_IDENTITY_INTERNAL_KEY"):
    print("ERROR: ARKI_IDENTITY_INTERNAL_KEY no disponible en entorno")
    sys.exit(2)

# ---------------------------------------------------------------------------
# 2. Importar app (con ROOTS ya resueltos por las env vars)
# ---------------------------------------------------------------------------
sys.path.insert(0, "/opt/arki-bridge")
import mcp_server_entry
from mcp_server_entry import mcp

# ---------------------------------------------------------------------------
# 3. Token ARKI para las tools (generado por el padre, no aquí)
# ---------------------------------------------------------------------------
TOKEN = (os.environ.get("ARKI_TEST_TOKEN") or "").strip()
if not TOKEN:
    print("ERROR: ARKI_TEST_TOKEN no disponible")
    sys.exit(2)

# ---------------------------------------------------------------------------
# 4. Mapa: 1 prueba por tool. 49 registradas + 1 esperada (get_git_diff)
# ---------------------------------------------------------------------------
TOOL_ARGS = {
    # --- 6 originales ---
    "get_bridge_health": {},
    "get_repo_status": {},
    "get_git_status": {"repo": "sicl-web"},
    "get_git_branch": {"repo": "sicl-web"},
    "get_git_head": {"repo": "sicl-web"},
    "get_services_status": {},
    # --- 43 del bloque ---
    "get_git_log": {"repo": "sicl-web"},
    "get_git_log_oneline": {"repo": "sicl-web"},
    "get_git_log_graph": {"repo": "sicl-web"},
    "get_git_log_author": {"repo": "sicl-web"},
    "get_git_log_dates": {"repo": "sicl-web"},
    "get_git_last_commit": {"repo": "sicl-web"},
    "get_git_commit_stats": {"repo": "sicl-web"},
    "get_git_commit_files": {"repo": "sicl-web"},
    "get_git_commit_summary": {"repo": "sicl-web"},
    "get_git_commit_count": {"repo": "sicl-web"},
    "get_git_branches": {"repo": "sicl-web"},
    "get_git_branches_all": {"repo": "sicl-web"},
    "get_git_branch_verbose": {"repo": "sicl-web"},
    "get_git_branch_merged": {"repo": "sicl-web"},
    "get_git_branch_unmerged": {"repo": "sicl-web"},
    "get_git_tags": {"repo": "sicl-web"},
    "get_git_tags_latest": {"repo": "sicl-web"},
    "get_git_refs": {"repo": "sicl-web"},
    "get_git_remote": {"repo": "sicl-web"},
    "get_git_tracking_branch": {"repo": "sicl-web"},
    "get_git_changed_files": {"repo": "sicl-web"},
    "get_git_changed_names": {"repo": "sicl-web"},
    "get_git_diff_stat": {"repo": "sicl-web"},
    "get_git_diff_names": {"repo": "sicl-web"},
    "get_git_diff_cached": {"repo": "sicl-web"},
    "get_git_diff_cached_stat": {"repo": "sicl-web"},
    "get_git_status_porcelain": {"repo": "sicl-web"},
    "get_git_untracked": {"repo": "sicl-web"},
    "get_git_staged": {"repo": "sicl-web"},
    "get_git_conflicts": {"repo": "sicl-web"},
    "get_repo_root": {"repo": "sicl-web"},
    "get_repo_git_dir": {"repo": "sicl-web"},
    "get_repo_object_format": {"repo": "sicl-web"},
    "get_repo_shallow": {"repo": "sicl-web"},
    "get_repo_tree": {"repo": "sicl-web"},
    "get_repo_tree_root": {"repo": "sicl-web"},
    "get_repo_files": {"repo": "sicl-web"},
    "get_repo_readme": {"repo": "sicl-web"},
    "get_repo_docs": {"repo": "sicl-web"},
    "get_repo_submodules": {"repo": "sicl-web"},
    "get_repo_tracked_directories": {"repo": "sicl-web"},
    "get_repo_recent_files": {"repo": "sicl-web"},
    "get_repo_contributors": {"repo": "sicl-web"},
    # --- 1 esperada pero no registrada (para confirmar MISSING) ---
    "get_git_diff": {"repo": "sicl-web", "staged": False},
}

RESULTS = []


def extract_text(result):
    if not isinstance(result, dict):
        return str(result)
    for item in result.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            return item.get("text", "")
    return json.dumps(result, ensure_ascii=False)[:500]


async def run_one(name, args):
    full = dict(args)
    if name != "get_bridge_health":
        full["token"] = TOKEN
    try:
        result = await mcp.call_tool(name, full)
        text = extract_text(result)
        if "Error calling tool" in text:
            return "FAIL", text[:200]
        if "Unknown tool" in text:
            return "MISSING", text[:200]
        if not text.strip() or text.strip() == "{}":
            return "EMPTY", "resultado vacío"
        return "PASS", text[:120]
    except Exception as e:
        err = str(e)
        if "Unknown" in err or "not found" in err.lower():
            return "MISSING", err[:200]
        return "FAIL", err[:200]


async def main():
    print("=" * 78)
    print("ARKI MCP — 50 PRUEBAS (1 POR TOOL)")
    print("=" * 78)
    print("Fecha:", datetime.now().isoformat(timespec="seconds"))
    print("Usuario:", os.environ.get("USER", "?"))
    print("Token:", "len=" + str(len(TOKEN)))
    print("ARKI_BRIDGE_TOKEN:", "✓" if os.environ.get("ARKI_BRIDGE_TOKEN") else "✗")
    print("ARKI_IDENTITY_INTERNAL_KEY:", "✓" if os.environ.get("ARKI_IDENTITY_INTERNAL_KEY") else "✗")
    print()

    registered = await mcp.list_tools()
    names_reg = {t.name for t in registered}
    print(f"Tools registradas en runtime: {len(names_reg)}")
    print(f"Tools a probar: {len(TOOL_ARGS)}")
    print()

    for name in sorted(TOOL_ARGS):
        if name not in names_reg:
            RESULTS.append((name, "MISSING", "no registrada en runtime"))
            print(f"MISSING  | {name}")
            continue
        status, detail = await run_one(name, TOOL_ARGS[name])
        RESULTS.append((name, status, detail))
        print(f"{status:8s} | {name}")

    print()
    print("=" * 78)
    print("RESUMEN")
    print("=" * 78)
    from collections import Counter
    counts = Counter(s for _, s, _ in RESULTS)
    for k in ("PASS", "EMPTY", "FAIL", "MISSING"):
        print(f"{k:8s}: {counts.get(k, 0)}")
    print(f"TOTAL   : {len(RESULTS)}")

    print()
    print("=" * 78)
    print("DETALLE DE NO-PASS")
    print("=" * 78)
    for n, s, d in RESULTS:
        if s != "PASS":
            print(f"\n{s}: {n}")
            print(f"  {d}")

    with open("/tmp/arki_50_pruebas_result.json", "w") as f:
        json.dump(
            {"total": len(RESULTS), "counts": dict(counts),
             "results": [{"tool": n, "status": s, "detail": d} for n, s, d in RESULTS]},
            f, indent=2, ensure_ascii=False)
    print("\nEvidencia: /tmp/arki_50_pruebas_result.json")

    failed = counts.get("FAIL", 0) + counts.get("MISSING", 0) + counts.get("EMPTY", 0)
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
