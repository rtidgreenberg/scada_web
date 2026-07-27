"""scada_web — Level 2 SCADA web gateway.

Exposes DDS data to web clients over REST/WebSocket with a declarative
mapping layer that decouples the client view schema from the wire type.

Architecture (Purdue model placement: Level 2 — supervisory):
    config      — YAML-driven declaration of participants, topics, mappings
    discovery   — wire type learning from DDS builtin discovery (no local IDL)
    gateway     — DDS subscription manager; creates readers from config + learned types
    interest    — per-client uid refcounting (ADD on 0→1, DELETE on 1→0)
    mapping     — wire DynamicData → slim view JSON (union projection, rename, flatten)
    server      — REST + WebSocket (FastAPI/uvicorn)
"""
