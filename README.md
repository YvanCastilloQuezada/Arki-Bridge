# arki-bridge

API local restringida para ARKI-01. FastAPI + uvicorn, loopback-only.

## Estado
- Auth: doble camino (Bearer estático + tokens ARKI Identity vía introspección loopback)
- Bind: 127.0.0.1:18769
- Storage: sin BD propia (lee repos canónicos)

## Instalación
Copiar a `/opt/arki-bridge/`, virtualenv en `/opt/arki-bridge/venv/`,
servicio systemd `arki-bridge.service`.

## Tests
    python3 -m pytest tests/ -q
