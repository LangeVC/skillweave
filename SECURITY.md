# Security Policy

## Reporting

If you discover a security issue, please report it privately before public disclosure.

## Scope

Especially relevant for this repository:

- prompt injection risks in skills
- unsafe file loading
- unsafe script execution
- path traversal
- untrusted third-party skill content

## Current stance

This repository is an early MVP. Avoid production deployment of any execution layer without:

- strict sandboxing
- controlled tool access
- input validation
- audited script execution
- provenance tracking for external skill content
