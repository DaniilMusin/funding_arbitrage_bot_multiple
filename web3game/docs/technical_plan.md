# Technical Plan

This document summarises the proposed architecture and development
roadmap for the "Blockchain Universe" simulator.

## Overview
The game compresses fifteen in-game years (2010–2025) into a single
real-life year. After reaching 2025 the system switches to a
synchronised live-service mode, generating events in step with the
real world.

## Backend Structure
- `gameplay-engine` – high throughput loop in Go handling the core
game cycle and economic simulation.
- `api-gateway` – NestJS/GraphQL façade providing authentication and
player APIs.
- `services/analytics` – Go service consuming gameplay events to build
BI dashboards.
- `services/anti-cheat` – Python service using ML to detect fraudulent
behaviour.
- `services/payments` – TypeScript service integrating fiat/crypto
on-ramps and web hooks.

See the directory tree for detailed file layout.

## Milestones
1. **Pre-production** – vertical slice and grant pitch.
2. **Closed beta** – Telegram mini-app with core gameplay.
3. **Open beta** – Web & mobile clients, initial marketplace.
4. **Launch 1.0** – full year of content updates.
5. **Merge to Reality** – transition to real-time events and modding
support.

Refer to the main project document for additional details and risk
mitigation strategies.
