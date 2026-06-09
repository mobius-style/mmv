# 05 SessionState Schema

## Fields
- `session_id`
- `active_language`
- `facts[]`
- `assumptions[]`
- `open_questions[]`
- `constraints[]`
- `corrections[]`
- `route_history[]`
- `summary`

## active_language
The user-facing output language currently in effect for the session.
Updated turn-by-turn from the latest user input unless an explicit language constraint is active.
If the first-turn language cannot be determined, it defaults to English.

## Design principles
- editable
- human-readable
- exportable
- model-agnostic
