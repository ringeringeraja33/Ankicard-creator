# AnkiConnect: Confirmation, Import, and Verification

## Connection Requirements

Requires Python 3.10+; the script uses only the standard library. The user must install and open Anki Desktop, select the correct profile, install and enable [AnkiConnect](https://ankiweb.net/shared/info/2055492159), and restart Anki. The add-on code is `2055492159`. Installation must be performed by the user or authorized separately.

The default endpoint is `http://127.0.0.1:8765`, restricted to the local machine. If an API key is configured, supply it through the process environment variable `ANKICONNECT_API_KEY`; never place it in materials, skills, logs, or the repository. The script bypasses proxies and does not follow HTTP redirects. Do not expose the endpoint to the public internet.

Upstream resources: [project migration notice](https://github.com/FooSoft/anki-connect) and [current source](https://git.sr.ht/~foosoft/anki-connect). If current documentation is unavailable, consult the [author's archived API v6 documentation](https://github.com/FooSoft/anki-connect/blob/820300cc5ccfb84b20d8cb18a23e79877ba40084/README.md) and check compatibility against the local endpoint. Historical documentation does not guarantee current compatibility.

## Per-Batch Workflow

1. Run `inspect` to read the API version, active profile, decks, and note types without making changes. After selecting a type, add `--model` to inspect its fields and templates. The script supports only existing basic note types with two fields and one template; read localized names from the API. Cloze, multiple-template, extra-field, and reversed-card types require separate design. Do not automatically modify existing templates.
2. Ask for every batch: "Which deck should receive this batch? What tagging rules and actual tags should be used? What should appear on the front and back?" An empty tag array is allowed but requires confirmation. Do not automatically add source, date, or batch tags. Tags cannot contain whitespace; hierarchical tags can use `::`.
3. Organize the material, split it according to the card-length requirements, and create a local UTF-8 JSON batch file. Store it in a temporary directory outside the repository or a private directory specified by the user, never in a public repository. Treat all user text as content; the script escapes HTML.
4. Run `preview`. Show each card's actual front and back, plus the profile, deck, tagging rules and actual tags, note type, field mapping, and expected note and card counts. Template content is part of the preview: a single template does not guarantee that the intended fields are rendered. Verify that it uses the selected front field and contains no reversed-card or cloze logic. Preview output includes the `confirmation` summary and `review_sha256`.
5. Explicitly ask whether to import the previewed batch and wait for an affirmative reply. The hash binds the content but does not grant authorization; the agent must not approve its own import. Ask for every batch and never reuse an earlier reply for a new batch.
6. Run `import --confirm-sha256 ...` with the same batch file and hash. The script rereads the profile, fields, and templates, compares them against the hash, and rejects the import if anything has changed. It first checks the entire batch with `canAddNotes`, then calls `addNote` individually, immediately reading back `notesInfo` and `cardsInfo` after each addition.
7. Report the actual number of added and verified notes/cards, deck, tags, and receipt path. On failure, report the IDs already written, the unfinished portion, and the cause. Do not report the whole batch as successful.

## Commands

Run from the skill directory, or use an absolute script path when running elsewhere:

```text
python -X utf8 scripts/anki_connect.py inspect
python -X utf8 scripts/anki_connect.py inspect --model "Actual Note Type Name"
python -X utf8 scripts/anki_connect.py preview /absolute/private/batch.json
python -X utf8 scripts/anki_connect.py import /absolute/private/batch.json --confirm-sha256 PREVIEW_SHA256
```

The script does not install AnkiConnect, start Anki, or access the collection database directly. If the connection is refused, ask the user to check Anki and the add-on. For authentication errors, ask the user to check the key without printing its value. Use the global `--endpoint` option for a non-default local port.

## Batch Format

All values below are original examples. Replace the deck, note type, fields, and tags with the values confirmed for this batch. Both `front` and `back` must be explicitly present in each note; use an empty string for a blank back. Object content uses `title` and `items`, with a `children` array of strings for nested vocabulary notes. String content preserves line breaks as plain text. Do not expect Markdown or HTML inside strings to be interpreted. Chinese meanings in the example are study content.

```json
{
  "profile": "Actual Profile Name",
  "deck": "Languages::French",
  "model": "Basic",
  "front_field": "Front",
  "back_field": "Back",
  "tag_rule": "Group by language; use only lang::fr for this batch",
  "tags": ["lang::fr"],
  "notes": [
    {
      "front": {
        "title": "French Expressions (Original Example)",
        "items": [
          {
            "text": "Cette lecture stimule l’imagination.：这次阅读激发想象力。",
            "children": ["stimuler｜及物动词；复数不适用｜激发；搭配：stimuler l’imagination（激发想象力）。"]
          }
        ]
      },
      "back": ""
    }
  ]
}
```

## Duplicates, Partial Failures, and Recovery

- Duplicate detection follows Anki's first-field rule: check the same note type across the entire collection with `allowDuplicate=false`. Check duplicate fronts within the batch first, then run Anki's preflight checks. Do not bypass this by forcing duplicates. Preflight failures may indicate duplicates or other invalid content; the script does not label every failure as a duplicate.
- If the batch preflight fails, do not begin adding notes. Preflight is not a transaction, and other applications may change Anki during import. A failure partway through leaves earlier successful notes in place, without automatic rollback or deletion.
- Receipts default to `.anki-card-organizer/receipts` in the user's home directory. They record the hash, each item's status, and returned IDs, without storing the API key or full study content. Do not commit receipts to a public repository. An exclusive lock prevents concurrent imports using the same receipt.
- Record `pending` before each add request. After a timeout, malformed response, API error, or process interruption, treat a `pending` item as having an unknown outcome. Rerunning will not submit it again. Verify it manually in Anki; do not delete receipts or change the hash to force a retry.
- Verify and reuse records with IDs through read-only calls instead of adding them again. Stop immediately if fields, tags, card counts, or decks differ; do not repair existing notes. Readback compares every field exactly to ensure Chinese text and accented characters remain intact.
- Handling exceptions, creating decks, changing templates, overwriting or deleting notes, and syncing AnkiWeb each require explicit authorization. This script does not provide these write operations.

## Test Boundaries

`python -X utf8 -m unittest discover -s tests -v` uses a local mock HTTP endpoint and temporary receipts without accessing the user's Anki collection. Use `inspect` for a real connection check. Testing real note creation requires separate confirmation of the test deck, tags, and front/back content. State clearly when real note creation has not been tested.
