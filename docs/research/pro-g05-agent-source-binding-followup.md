# G05 agent-source binding follow-up

Your prior review found that `agents/openai.yaml` semantics were read outside the captured source snapshot and therefore could change routing without changing the receipt.

The attached current files now implement that exact correction:

- derive each evolution skill's agent-card path only after surface membership and skill declarations have been validated;
- read every agent-card path once into the same private `sourceBytes` map;
- parse each agent card only from `sourceText(path)` backed by those captured bytes;
- construct sorted `sourceDigests` from all captured entries, including the 15 agent cards;
- keep the recursive freeze, read-only Map facades, surface-membership guard, and inventory integrity behavior;
- add source-level regression coverage showing later agent-card drift cannot rewrite an existing loaded snapshot and does change a fresh load's receipt.

Please reread the attached latest `surface.mjs` and `surface-receipts.test.mjs`. Return only concrete material blockers in the bounded G05 repair, with the smallest local fix. If your prior blocker is closed and no other blocker remains, answer `PASS` plainly. Do not assume tests ran and do not request evidence artifacts.
