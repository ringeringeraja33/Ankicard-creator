# Anki Card Organizer

Turn language materials into concise Anki study cards and import them through local AnkiConnect after confirming each batch.

## Features

- Source titles, original-text bullet points, Chinese meanings, and essential explanations; indented B2–C1 vocabulary notes include parts of speech, plural forms, and common collocations.
- Expression-comparison cards put each expression on its own left-aligned front line, with indented explanations of grammar, usage, and meaning on the back. Titles retain their alignment; all body content is left-aligned.
- Approximately 4–6 source points per card, adjusted for vocabulary density; longer materials are split across cards.
- Confirmation of the deck, tagging rules, and front/back content for every batch, with a complete preview before import.
- Checks of the active profile, note type, fields, and templates; a confirmation hash binds the batch content and settings.
- Duplicate preflight checks using Anki's first-field rule, individual note creation, and readback verification of fields, tags, decks, and card counts.
- Local receipts track partial success and unknown outcomes without automatically retrying uncertain writes. Existing notes are never overwritten, and AnkiWeb sync is never automatic.

## Install as an Agent Skill

Copy the repository's `anki-card-organizer` folder into a skill directory supported by your agent, such as the workspace's `.agents/skills/` or your personal `~/.codex/skills/`. Preserve the directory structure and start with [SKILL.md](anki-card-organizer/SKILL.md).

Preparing card text does not require Anki. Direct import requires Python 3.10+, Anki Desktop running, and [AnkiConnect](https://ankiweb.net/shared/info/2055492159) enabled. The default endpoint is `http://127.0.0.1:8765`. The script uses only the Python standard library and calls the AnkiConnect API; it does not bundle the add-on.

See the [AnkiConnect workflow](anki-card-organizer/references/ankiconnect.md) for connection details, the batch JSON format, confirmation commands, and recovery rules.

## Usage

Ask your agent: "Organize these materials into language study cards and add them to Anki. First ask me about the deck, tagging rules, and front/back content."

Run a read-only connection check or the tests from the repository root:

```text
python -X utf8 anki-card-organizer/scripts/anki_connect.py inspect
python -X utf8 -m unittest discover -s anki-card-organizer/tests -v
```

The confirmation hash prevents changes after preview. The agent must obtain the user's authorization in the conversation; the hash itself does not grant permission.

## Scope and Privacy

The importer supports existing basic note types with two fields and one template, including localized field names and an empty back. Cloze cards, reversed cards, multiple templates, extra fields, media downloads, deck creation, template changes, deletion, overwriting, and AnkiWeb sync are outside the current automatic import scope.

Keep private materials and batch JSON files outside the repository. Receipts default to `.anki-card-organizer/receipts/` in the user's home directory. Supply API keys only through the `ANKICONNECT_API_KEY` environment variable. Do not commit keys, receipts, or study content. Tests use original examples and an isolated mock HTTP server without accessing a real Anki collection.

Archived API documentation may differ from the installed version. Stop if `inspect` or a subsequent read-only call encounters an unsupported method; never fall back to direct database writes. Do not switch Anki profiles or edit the relevant templates during import.
