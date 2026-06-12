# Continuity 1.1 Plan

## Thesis

Memoria stores facts. Continuity stores the current position formed by those
facts.

Continuity 1.1 is not a larger memory system. It tightens the bridge between
long-term facts and the current session so an agent can answer:

```text
Why am I continuing from here?
```

## Scope

1. Preserve provenance for the current position.
   - Record which observed facts or memory IDs were used.
   - Keep the source thread, handoff, and actor visible.

2. Separate facts from interpretation.
   - `facts_used` stores references to observed facts.
   - `current_interpretation` stores the current session position.
   - `next_step` remains the action-oriented continuation point.

3. Add lifecycle for interpretation.
   - Interpretations can be `active`, `needs_review`, `stale`, or `closed`.
   - User-confirmed interpretations are marked explicitly.

4. Add packet guardrails.
   - Every Continuity Packet should remind the agent that Continuity is current
     position, not durable fact.
   - Agents should write to Memoria only when the content is observable fact.

5. Keep Memoria independent.
   - Continuity can reference Memoria facts.
   - Memoria should not depend on Continuity or store Continuity's current
     interpretation as fact.

## First Implementation Slice

- Add `facts_used`, `current_interpretation`, `interpretation_status`, and
  `user_confirmed` to Session Thread.
- Expose those fields through `capture`, `edit`, `show`, `resume`, and JSON
  packet output.
- Update docs to describe the Memoria/Continuity boundary.
- Leave automatic Memoria recall and Web UI editing for a later slice.

Status: completed.

## Second Implementation Slice

- Show provenance and interpretation status in the Web management view.
- Allow editing `facts_used`, `current_interpretation`, `interpretation_status`,
  and `user_confirmed` from the Web UI.
- Add CLI and API filtering by `interpretation_status`.

Status: completed.

## Later Slices

- Allow a packet to include selected Handoff provenance.
- Add a small helper that suggests Memoria facts to reference without writing
  them into Continuity automatically.
