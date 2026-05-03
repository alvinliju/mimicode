# memory_recall fixture

Pre-seeded `.mimi/memory/` simulating a long-running project. Used to test
whether the agent uses `memory_search` to recall prior decisions instead of
reading source files (most of which don't even exist here).

Relevant entry: `auth_layer` component + `use-jwt-stateless` decision.
Distractors: `payment_processor`, `cache_layer`.

The agent passes this task by calling `memory_search` with an auth-related
query and surfacing the JWT/HMAC details in its final answer.
