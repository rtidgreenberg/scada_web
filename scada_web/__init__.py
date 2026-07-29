"""scada_web — Level 2 SCADA web gateway.

Exposes DDS data to web clients over REST/WebSocket with typed views
that decouple the client JSON schema from the DDS wire type (DD-052/DD-053).

Architecture (Purdue model placement: Level 2 — supervisory):
    config      — YAML-driven declaration of participants, topics, QoS
    gateway     — DDS subscription manager; uses Python generated types
    interest    — per-client uid refcounting and global selector separation
    views       — typed DDS sample → slim view dataclass → JSON dict
    server      — REST + WebSocket (FastAPI/uvicorn)

Generated DDS types (rtiddsgen output for the PLC module) live in
dds/gen/, centralized so scada_web, sim, and tests all import the same
PLC types from one place (see dds/gen/PlcValue.py).
"""
