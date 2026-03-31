---
name: autorep-dispatch-experiment
description: Request clarification for the current AutoReplication work order, or send the formal result reply for the dispatch being handled in this session. Use when the experiment agent is blocked or ready to report results.
---

# AutoReplication Dispatch For Experiment

Use this skill only for cross-agent communication while handling a dispatch in the current session.

Available commands:

```bash
autorep-dispatch request-clarify --question "<question>"
autorep-dispatch reply --result-file <path>
```

Workflow:

1. If the current work order is blocked by missing information, ask exactly the clarification you need with `autorep-dispatch request-clarify`.
2. Once the missing information arrives, continue the same session.
3. When the work is complete, write a structured result JSON file and call `autorep-dispatch reply`.

Rules:

- Do not open free-form side conversations with another agent.
- Do not invent dispatch ids, session ids, or target routing fields.
- Ask only the minimum clarification needed to unblock execution.
- The final reply should state what happened, what artifacts exist, and whether the work completed.

Recommended final-reply payload shape:

```json
{
  "result": "completed",
  "summary": "What was done",
  "artifacts": [],
  "notes": []
}
```
