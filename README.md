# session-summary-title

An agent skill that summarizes a session and renames it to an **exactly twelve-Han-character** title — and that keeps a strict evidence boundary between *candidate*, *request accepted*, *persisted and read back*, and *UI updated*.

[中文说明](README.zh-CN.md)

Works with:

- **DeepSeek Harness** — through the `set_session_title` tool
- **Codex** — through the app-server `thread/name/set` RPC, or the `/rename` slash command

## Install

```bash
npx skills add CancerTiN/session-summary-title
```

Or copy `skills/session-summary-title/` into your agent's skill directory (`~/.agents/skills/`, `~/.claude/skills/`, …).

## Usage

Invoke the skill, or just ask in plain language:

> Summarize this session and rename it with a twelve-character Chinese title.

If you only ask for a summary, or only for title candidates, you get only that — the skill does not do more than it was asked.

## Why exactly twelve Han characters?

Twelve characters is roughly the length of a compact noun phrase: long enough to name both the *object* and the *deliverable*, short enough to stay readable in a sidebar or a tab strip. The constraint is enforced mechanically, not by vibes:

```bash
python3 skills/session-summary-title/scripts/validate_title.py '打通集群接入与飞书工具链'
# OK
```

The validator accepts a title only when it is exactly twelve characters *and* every character is a CJK unified ideograph. Spaces, punctuation, digits, Latin letters, emoji, radicals, and iteration marks are all rejected. Han detection goes through `unicodedata.name()`, so unassigned codepoints that sit inside old CJK ranges are correctly rejected while newer supplementary-plane ideographs are accepted.

## Design: the evidence boundary

Most "rename the session" flows report success the moment the API call returns. That collapses four very different states into one word:

| State | What is actually known |
| --- | --- |
| **Candidate** | A title was proposed. Nothing was written. |
| **Request accepted** | The write call returned success. The server may still drop it. |
| **Persisted** | An independent read-back of the same target shows the new title. |
| **UI updated** | The user's own interface reflects it. Observable only by the user. |

This skill refuses to collapse them. It reports *persisted* only after an independent read-back; if a tool confirms the write but read-back is impossible it reports *modified*; if the outcome is unknown it reports *unconfirmed* and hands the candidate back. It never claims a UI update it cannot observe.

The same discipline governs target selection. The rename tool acts on the caller's own session, and the runtime session ID is used **only** for read-back verification — never to guess a target, and never to fall back to a parent session when the current one is unreadable or absent.

## Layout

```
skills/session-summary-title/
├── SKILL.md                     instructions the agent loads
├── agents/openai.yaml           Codex-facing manifest
├── references/cli-protocol.md   Codex app-server protocol notes and evidence rules
└── scripts/
    ├── validate_title.py        the twelve-Han-character validator
    ├── rename_thread.py         the Codex app-server rename path
    └── test_*.py                unittest suite
```

## Requirements

- **Python 3** — the scripts use the standard library only, with no third-party packages
- **Codex CLI** — only if you use the Codex rename path; the DeepSeek Harness path needs nothing beyond the built-in tool

## Tests

```bash
cd skills/session-summary-title
python3 -B -m unittest discover -s scripts -p 'test_*.py'
```

27 tests covering validator edge cases (wrong length, non-Han characters, unassigned codepoints inside old ranges, supplementary-plane ideographs, radicals and iteration marks), target isolation (a subagent never renames its parent), protocol failures, write-attempt reporting, and read-back verification.

## License

MIT — see [LICENSE](LICENSE).
