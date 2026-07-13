# Integrated Requirement Management Program Upload

This branch contains the complete integrated requirement-management program package produced for the KB/EVT workstream.

The package is stored as base64 chunks because the ChatGPT GitHub connector can write text files reliably, but it cannot directly upload a local sandbox directory or binary zip as a file parameter.

## Restore

From repository root:

```bash
python scripts/restore_requirement_program.py
```

This recreates:

```text
artifacts/requirement_program_package/evt_requirement_resolver_integrated_program_system_audit.zip
```

To extract the package into the repository root:

```bash
python scripts/restore_requirement_program.py --extract
```

If files already exist and you intentionally want to overwrite them:

```bash
python scripts/restore_requirement_program.py --extract --overwrite
```

## Package contents

The restored package contains the integrated custom requirement-management program:

```text
Requirement Resolver
Compliance Matrix
Impact Analysis
Approval Governance
Candidate Extraction
Package Import
Project Baseline Versioning
Release Readiness Gate
ECO Workflow
System Integration Audit
Validation Orchestrator
```

## Package hash

```text
sha256: 8bab5be1a8f51bcdc08b2d8b55a0d6d37446c7f1aa22a7e3e7d3c993d62a8b56
```
