# ADR 001 — JISP is a Standalone, AI-First Spatial Intelligence Platform

- **Status**: Accepted
- **Date**: 2026-04-22

## Context

JISP must be positioned unambiguously relative to adjacent systems. There is
repeated pressure to blend JISP with field execution, mobile backends,
offline-first capture, or vendor data-warehouse stacks. This ADR locks the
positioning.

## Decision

JISP is a **pre-field**, **cloud-native**, **standalone** spatial intelligence
platform. Its sole purpose is to provide intelligence, prioritization, and
reasoning BEFORE field execution.

- JISP **does not** handle field data capture.
- JISP **does not** handle sync or edge workflows.
- JISP **does not** implement offline-first logic in its core.
- Offline-first capability, if ever needed, will be added as an external
  extension WITHOUT modifying the JISP core.

JISP is AI-first, geospatial-native, asset-centric, time-aware, and
explainable by design.

## Consequences

- The approved technology stack (see `docs/architecture/tech-stack.md`) is
  non-negotiable. No cloud services or vendor-lock frameworks are permitted.
- Folder responsibilities are strict (see `solution-architecture.md`).
  Cross-folder logic is not allowed.
- Any future offline-first work is out of scope for the core repository.
