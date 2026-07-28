"""scada_web — Level 2 SCADA web gateway.

Exposes DDS data to web clients over REST/WebSocket with a declarative
mapping layer that decouples the client view schema from the wire type.

Architecture (Purdue model placement: Level 2 — supervisory):
    config      — YAML-driven declaration of participants, topics, types, mappings
    gateway     — DDS subscription manager; loads types from XML, creates readers at startup
    interest    — per-client uid refcounting and global selector separation
    mapping     — wire DynamicData → slim view JSON (union projection, rename, flatten)
    server      — REST + WebSocket (FastAPI/uvicorn)
"""
