# Consensus Stability Report

Measured, not estimated — see tests/integration/test_stability.py. Published
as-is, including failures, per docs/SUBMISSION-STRATEGY.md's honesty requirement.

**Measured:** 2026-08-24T15:57:15.507536+00:00
**Target:** `https://www.githubstatus.com/`
**Question:** 'According to this page, are all systems currently operational?'
**Schema:** `ENUM:operational,degraded,outage`
**Network:** studio.genlayer.com (real leader + validators, real web/LLM calls)

## Result: 10/10 (100.0%)

## Raw data

```json
[
  {
    "run": 1,
    "consensus_succeeded": true,
    "status": "OK",
    "answer": "operational"
  },
  {
    "run": 2,
    "consensus_succeeded": true,
    "status": "OK",
    "answer": "operational"
  },
  {
    "run": 3,
    "consensus_succeeded": true,
    "status": "OK",
    "answer": "operational"
  },
  {
    "run": 4,
    "consensus_succeeded": true,
    "status": "OK",
    "answer": "operational"
  },
  {
    "run": 5,
    "consensus_succeeded": true,
    "status": "OK",
    "answer": "operational"
  },
  {
    "run": 6,
    "consensus_succeeded": true,
    "status": "OK",
    "answer": "operational"
  },
  {
    "run": 7,
    "consensus_succeeded": true,
    "status": "OK",
    "answer": "operational"
  },
  {
    "run": 8,
    "consensus_succeeded": true,
    "status": "OK",
    "answer": "operational"
  },
  {
    "run": 9,
    "consensus_succeeded": true,
    "status": "OK",
    "answer": "operational"
  },
  {
    "run": 10,
    "consensus_succeeded": true,
    "status": "OK",
    "answer": "operational"
  }
]
```
