---
description: Scout a company for funding, open AI/ML/SDE roles, and people to network with
argument-hint: <company website or name> [extra context]
---

Use the **company-scout** subagent to investigate: $ARGUMENTS

After the subagent returns, relay to me:
1. The heat rating and funding one-liner
2. Open matching roles (with links)
3. The top 2 people to approach and the drafted connection notes
4. The single best next action

If any person is marked `[verify on LinkedIn]` and my Chrome is connected,
offer to verify them and find mutual connections / school alumni (schools are
in config/network.json) via LinkedIn
(read-only — never send anything without my explicit go).
