# ECO Validation Gates

## Unit gates

```text
test_requirement_eco.py
test_requirement_eco_query_api.py
```

## Smoke gate

```text
smoke.eco
```

The smoke gate validates:

1. create ECO;
2. run impact analysis;
3. submit for approval;
4. approve;
5. apply requirement variant change;
6. freeze post-change baseline;
7. rerun DV release gate;
8. finish as `closed` or `gate_blocked` with audit artifacts.

## Acceptance

```text
72 unit tests OK
17 orchestrator smoke gates PASS
```
