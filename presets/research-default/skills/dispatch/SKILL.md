---
name: autorep-dispatch-research
description: Create bounded work orders for another AutoReplication agent, or formally answer clarification requests in the current session. Use when the research agent needs to delegate work or reply to a clarification.
---

# AutoReplication Dispatch For Research

Use this skill only for cross-agent communication. Do not talk to another agent in free-form prose.

Available commands:

```bash
autorep-dispatch work-order --to-agent <agent_id> --payload-file <path>
autorep-dispatch reply --result-file <path>
```

Workflow:

1. If you need another agent to execute a bounded task, write a JSON payload file and call `autorep-dispatch work-order`.
2. If this session receives a clarification request, write a JSON answer file and call `autorep-dispatch reply`.
3. After the dispatch command succeeds, continue the session normally. Do not invent routing ids or mention hidden runtime state.

Required payload discipline:

- Use structured JSON files, not inline prose.
- Keep work orders concrete, testable, and scoped to one execution session.
- Keep clarification replies direct and sufficient for the blocked work to continue.

Recommended work-order payload shape:

```json
{
  "title": "Short work order title",
  "goal": "Concrete execution goal",
  "artifacts": ["expected output"],
  "constraints": ["important constraint"]
}
```

Recommended clarification-reply payload shape:

```json
{
  "answer": "Direct answer",
  "summary": "What the answer changes"
}
```
