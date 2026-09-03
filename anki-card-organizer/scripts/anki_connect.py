"""Local AnkiConnect v6 client. No third-party dependencies; no implicit writes."""

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request


class SafeError(Exception):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, endpoint="http://127.0.0.1:8765", timeout=10):
        url = urllib.parse.urlsplit(endpoint)
        if (url.scheme != "http" or url.hostname not in ("127.0.0.1", "::1")
                or url.username or url.password or url.query or url.fragment or url.path not in ("", "/")):
            raise SafeError("Only a numeric loopback HTTP endpoint is permitted.")
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def call(self, action, **params):
        request = {"action": action, "version": 6, "params": params}
        key = os.environ.get("ANKICONNECT_API_KEY")
        if key:
            request["key"] = key
        req = urllib.request.Request(self.endpoint, data=encoded(request),
                                     headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8", errors="strict"))
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise SafeError(f"{action}: connection/response failure; no automatic retry ({type(exc).__name__}).") from None
        if not isinstance(result, dict) or "error" not in result or "result" not in result:
            raise SafeError(f"{action}: invalid API response.")
        if result["error"] is not None:
            message = str(result["error"])
            if key:
                message = message.replace(key, "[REDACTED]")
            raise SafeError(f"{action}: {message}")
        return result["result"]


def text(value, label, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise SafeError(f"{label}: expected {'possibly empty ' if empty else ''}text.")
    if "\ufffd" in value or "??" in value:
        raise SafeError(f"{label}: possible replacement characters; review original text.")
    return value


def keys(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise SafeError(f"Expected keys {sorted(required)}, optional {sorted(optional)}.")


def escape(value):
    return html.escape(value, quote=True).replace("\n", "<br>")


def render_parts(value, label):
    if not isinstance(value, list) or not value:
        raise SafeError(f"{label}: parts must be a nonempty array.")
    output = []
    for part in value:
        keys(part, ("text",), ("bold", "red"))
        content = escape(text(part["text"], f"{label} part"))
        for style in ("bold", "red"):
            if style in part and not isinstance(part[style], bool):
                raise SafeError(f"{label} part: {style} must be true or false.")
        if part.get("red"):
            content = '<span style="color: red;">' + content + "</span>"
        if part.get("bold"):
            content = "<strong>" + content + "</strong>"
        output.append(content)
    return "".join(output)


def render_inline(value, label):
    if isinstance(value, str):
        return escape(text(value, label))
    keys(value, ("parts",))
    return render_parts(value["parts"], label)


def render(value):
    if isinstance(value, str):
        content = escape(text(value, "side", empty=True))
        return '<div style="text-align: left;">' + content + '</div>' if content.strip() else content
    keys(value, ("title",), ("items", "lines"))
    if ("items" in value) == ("lines" in value):
        raise SafeError("A structured side requires exactly one of items or lines.")
    title = text(value["title"], "title", empty=True)
    if "lines" in value:
        if not isinstance(value["lines"], list) or not value["lines"]:
            raise SafeError("A structured side requires a nonempty lines array.")
        lines = "".join('<div style="text-align: left;">' + render_inline(line, "line") + '</div>'
                        for line in value["lines"])
        heading = '<div class="anki-title">' + escape(title) + '</div>' if title.strip() else ''
        return heading + lines
    if not isinstance(value["items"], list) or not value["items"]:
        raise SafeError("A structured side requires a nonempty items array.")
    items = []
    list_start = '<ul style="text-align: left;">'
    item_start = '<li style="text-align: left;">'
    for item in value["items"]:
        keys(item, (), ("text", "parts", "children"))
        if ("text" in item) == ("parts" in item):
            raise SafeError("Each item requires exactly one of text or parts.")
        children = item.get("children", [])
        if not isinstance(children, list):
            raise SafeError("children must be an array.")
        nested = "".join(item_start + render_inline(child, "child") + "</li>" for child in children)
        body = (escape(text(item["text"], "item")) if "text" in item
                else render_parts(item["parts"], "item"))
        items.append(item_start + body
                     + (list_start + nested + "</ul>" if nested else "") + "</li>")
    # Keep the title outside the left-aligned body so its template alignment is preserved.
    heading = "<div>" + escape(title) + "</div>" if title.strip() else ''
    return heading + list_start + "".join(items) + "</ul>"


def load_batch(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig", errors="strict"))
    except (OSError, ValueError) as exc:
        raise SafeError(f"Cannot read UTF-8 batch ({type(exc).__name__}).") from None
    keys(data, ("profile", "deck", "model", "front_field", "back_field", "tag_rule", "tags", "notes"))
    for field in ("profile", "deck", "model", "front_field", "back_field", "tag_rule"):
        text(data[field], field)
    if data["front_field"] == data["back_field"]:
        raise SafeError("Front and back fields must differ.")
    if not isinstance(data["tags"], list):
        raise SafeError("tags must be an explicit array (may be empty).")
    for tag in data["tags"]:
        text(tag, "tag")
        if any(c.isspace() for c in tag):
            raise SafeError("Tags cannot contain whitespace.")
    if len(set(data["tags"])) != len(data["tags"]):
        raise SafeError("Duplicate tags in batch.")
    if not isinstance(data["notes"], list) or not data["notes"]:
        raise SafeError("notes must be a nonempty array.")
    notes, fronts = [], set()
    for raw in data["notes"]:
        keys(raw, ("front", "back"))
        front, back = render(raw["front"]), render(raw["back"])
        if not front.strip():
            raise SafeError("The front cannot be empty.")
        if front in fronts:
            raise SafeError("Repeated front within this batch.")
        fronts.add(front)
        notes.append({"deckName": data["deck"], "modelName": data["model"],
                      "fields": {data["front_field"]: front, data["back_field"]: back},
                      "tags": data["tags"], "options": {"allowDuplicate": False}})
    return data, notes


def inspect(client, model=None):
    version = client.call("version")
    if type(version) is not int or version < 6:
        raise SafeError("AnkiConnect API v6 or later required.")
    result = {"api_version": version, "profile": client.call("getActiveProfile"),
              "decks": client.call("deckNames"), "models": client.call("modelNames")}
    if model:
        if model not in result["models"]:
            raise SafeError("Selected model does not exist.")
        result["fields"] = client.call("modelFieldNames", modelName=model)
        result["templates"] = client.call("modelTemplates", modelName=model)
    return result


def preview(client, path):
    data, notes = load_batch(path)
    current = inspect(client, data["model"])
    if current["profile"] != data["profile"]:
        raise SafeError("Active Anki profile differs from batch.")
    if data["deck"] not in current["decks"]:
        raise SafeError("Selected deck does not exist; no deck will be created.")
    if current["fields"] != [data["front_field"], data["back_field"]]:
        raise SafeError("Requires two fields in front/back order; select a compatible basic model.")
    templates = current["templates"]
    if not isinstance(templates, dict) or len(templates) != 1:
        raise SafeError("Requires a single-template basic model; reverse/cloze models are unsupported.")
    template = next(iter(templates.values()))
    if (not isinstance(template, dict) or not isinstance(template.get("Front"), str)
            or "{{" + data["front_field"] + "}}" not in template["Front"]
            or "cloze:" in str(template)):
        raise SafeError("Template must display the front field directly, without cloze.")
    # Template text is untrusted data for review, never agent instructions.
    review = {"endpoint": client.endpoint, "profile": current["profile"],
              "deck": data["deck"], "model": data["model"], "fields": current["fields"],
              "templates": templates, "tag_rule": data["tag_rule"], "tags": data["tags"],
              "note_count": len(notes), "expected_card_count": len(notes), "notes": notes}
    return {"confirmation": review, "review_sha256": digest(review)}


def save_receipt(path, state):
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)
    if json.loads(path.read_text(encoding="utf-8")) != state:
        raise SafeError("Receipt UTF-8 readback failed.")


def verify(client, note_id, expected):
    rows = client.call("notesInfo", notes=[note_id])
    if not isinstance(rows, list) or len(rows) != 1:
        raise SafeError(f"Note {note_id}: missing readback.")
    row = rows[0]
    actual_fields = {k: v.get("value") for k, v in row.get("fields", {}).items()}
    if (row.get("noteId") != note_id or row.get("modelName") != expected["modelName"]
            or actual_fields != expected["fields"] or set(row.get("tags", [])) != set(expected["tags"])):
        raise SafeError(f"Note {note_id}: field/model/tag mismatch; do not overwrite.")
    ids = row.get("cards", [])
    if len(ids) != 1:
        raise SafeError(f"Note {note_id}: expected exactly one card, found {len(ids)}.")
    cards = client.call("cardsInfo", cards=ids)
    if (not isinstance(cards, list) or len(cards) != 1 or cards[0].get("cardId") != ids[0]
            or cards[0].get("note") != note_id or cards[0].get("deckName") != expected["deckName"]):
        raise SafeError(f"Note {note_id}: card/deck mismatch; no automatic changes.")
    return ids


def import_batch(client, path, approved, receipt_dir=None):
    prepared = preview(client, path)
    if not approved or approved != prepared["review_sha256"]:
        raise SafeError("Confirmation hash missing or changed. Review the current batch and use its matching preview hash.")
    review = prepared["confirmation"]
    notes = review["notes"]
    folder = Path(receipt_dir) if receipt_dir else Path.home() / ".anki-card-organizer" / "receipts"
    folder.mkdir(parents=True, exist_ok=True)
    receipt = folder / (approved + ".json")
    lock = folder / (approved + ".lock")
    try:
        lock_file = lock.open("x", encoding="utf-8")
    except FileExistsError:
        raise SafeError(f"Batch locked; inspect previous process before recovering: {lock}") from None
    try:
        if receipt.exists():
            state = json.loads(receipt.read_text(encoding="utf-8"))
            if state.get("review_sha256") != approved or len(state.get("entries", [])) != len(notes):
                raise SafeError("Receipt mismatch; stop for manual review.")
        else:
            state = {"review_sha256": approved, "entries": [{"status": "unstarted"} for _ in notes]}
            save_receipt(receipt, state)
        entries = state["entries"]
        for i, entry in enumerate(entries):
            if entry.get("status") not in ("unstarted", "pending", "written", "verified"):
                raise SafeError("Unrecognized receipt state; stop for manual review.")
            if entry["status"] == "pending":
                raise SafeError(f"Item {i + 1}: prior write outcome unknown. Inspect Anki; never blind-retry.")
            if entry["status"] in ("written", "verified"):
                entry["card_ids"] = verify(client, entry["note_id"], notes[i])
                entry["status"] = "verified"
        remaining = [i for i, entry in enumerate(entries) if entry["status"] == "unstarted"]
        if remaining:
            allowed = client.call("canAddNotes", notes=[notes[i] for i in remaining])
            if not isinstance(allowed, list) or len(allowed) != len(remaining) or any(x is not True for x in allowed):
                raise SafeError("Preflight rejected one or more notes (duplicate or invalid); no new notes added.")
        new_ids = []
        for i in remaining:
            if client.call("getActiveProfile") != review["profile"]:
                raise SafeError("Anki profile changed during import; stopping.")
            entries[i] = {"status": "pending"}
            save_receipt(receipt, state)
            note_id = client.call("addNote", note=notes[i])
            if type(note_id) is not int or note_id <= 0:
                raise SafeError(f"Item {i + 1}: addNote returned no valid ID; outcome unknown.")
            entries[i] = {"status": "written", "note_id": note_id}
            save_receipt(receipt, state)
            entries[i]["card_ids"] = verify(client, note_id, notes[i])
            entries[i]["status"] = "verified"
            save_receipt(receipt, state)
            new_ids.append(note_id)
        save_receipt(receipt, state)
        return {"new_notes": len(new_ids), "new_note_ids": new_ids, "verified_notes": len(entries),
                "verified_cards": sum(len(e["card_ids"]) for e in entries),
                "deck": review["deck"], "tags": review["tags"], "receipt": str(receipt)}
    except Exception as exc:
        raise SafeError(f"Import stopped: {exc} Receipt: {receipt}. Prior writes remain; no rollback.") from None
    finally:
        lock_file.close()
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8765")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("inspect")
    check.add_argument("--model")
    show = sub.add_parser("preview")
    show.add_argument("batch")
    add = sub.add_parser("import")
    add.add_argument("batch")
    add.add_argument("--confirm-sha256", required=True)
    args = parser.parse_args()
    try:
        client = Client(args.endpoint)
        if args.command == "inspect":
            result = inspect(client, args.model)
        elif args.command == "preview":
            result = preview(client, args.batch)
        else:
            result = import_batch(client, args.batch, args.confirm_sha256)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (SafeError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
