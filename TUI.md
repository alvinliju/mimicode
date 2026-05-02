# Mimicode TUI

Built with [Textual](https://github.com/Textualize/textual). Launch via:

```bash
python agent.py --tui [-s session_id]
```

## Structure

```
MimicodeApp (App)
├── Label                  session title bar
├── ChatHistory            scrollable message log (VerticalScroll)
│   └── MessageBox(s)      one per message — markup=False to avoid Rich crash on brackets
├── ThinkingIndicator      shown while agent is working (CSS display toggle)
├── PromptInput            text input, docked to bottom
└── Footer                 keybinding hints
```

## Key details

- `MessageBox` extends `Static` with `markup=False` — required because tool output contains `[` `]` which Rich parses as markup tags and crashes
- Agent runs in `async` via `agent_turn()`, input is disabled while processing
- Messages persist to `sessions/<id>.messages.json` and resume on next launch with `-s session_id`
- Keybindings: `ctrl+c` / `ctrl+d` to quit
