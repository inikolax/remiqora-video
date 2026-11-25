"""What to make from a graph's «Идея» node: a video prompt, a picture prompt, a draft script or a free talk with the writer.

The two prompt modes reuse the translator (translate.py: its system prompt for the scene model, Krea 2 or FLUX.2 Klein);
the script and the talk are written here. `plan()` decides which prompts are made and which of the idea's wires each takes,
so the page only applies the answer. An LLM runs only by the user's button (a job in the GPU queue).
"""
from __future__ import annotations

from typing import Optional

from .. import i18n
from . import client, translate

MODES = ("video", "picture", "script", "think")
# added to the still's system prompt when the user asks for a picture prompt from an idea: the owner's habits for pictures
PICTURE_EXTRA = """

Also, for this prompt:
- No motion words at all (walking, running, turning, flying, flowing, slowly, then, while, starts to), no camera moves (pan, zoom, dolly, tracking), no time words (seconds, later, suddenly): one frozen frame.
- Name the shot size, the framing and the lens (e.g. "medium close-up, 50mm, shallow depth of field").
- Describe a person only by what is seen and what the idea says. Never add "beautiful", "pretty", "feminine", "attractive" or a gender the idea does not give.
- End with: "No text, no letters, no logos, no watermark." (unless the idea asks for a written sign or screen)."""

PROMPT_MODES = ("video", "picture")

SCRIPT_SYSTEM = """You are a screenwriter. You turn the idea of a short video, written in Russian, into a short draft script by scenes, for the person who will read it, edit it and give it to the video writer.

Rules:
- 3 to 8 scenes, each one a single place and a single moment of the story, in order; the last one is the ending.
- For every scene: "where" (the place and time of day), "who" (who is in the frame, a few words), "what" (what happens, in one or two plain, concrete sentences: what is seen and done).
- Keep what the idea says: its people, place, mood and ending; do not add a different story. Add only what the idea leaves open (the in-between scenes, the small concrete details).
- Write everything in Russian, plain words. No camera jargon, no prompts for a model, no English unless the idea has it.
- "title": a short name of the video, 2 to 6 words."""

SCRIPT_SCHEMA = {"type": "object", "properties": {
    "title": {"type": "string"},
    "scenes": {"type": "array", "items": {"type": "object", "properties": {
        "where": {"type": "string"}, "who": {"type": "string"}, "what": {"type": "string"}},
        "required": ["where", "who", "what"], "additionalProperties": False}}},
    "required": ["title", "scenes"], "additionalProperties": False}

THINK_SYSTEM = """You are a screenwriter talking to the person who gave you the idea of a short video, written in Russian. Do not write the script and do not write a prompt: think aloud about the idea.

Answer in Russian, plain words, in 120-250 words, in short paragraphs or a short list:
- two or three different ways to tell it (what each one gives);
- what in the idea could work best and why;
- the pitfalls: what a video model usually gets wrong here (text in the frame, too many people, long speech, fast complex action, hands, a face in a crowd) and how to avoid it;
- one question, if something in the idea decides the result and it is not clear.
Do not praise the idea. Stay with what the idea says."""

THINK_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"], "additionalProperties": False}

LABELS = {"ru": ("Сцена", "Где", "Кто", "Что происходит"), "en": ("Scene", "Where", "Who", "What happens")}


def default_mode(kinds: list[str]) -> str:
    """The mode by what the idea feeds: only pictures -> «picture», anything else (scenes, nothing, both) -> «video»."""
    return "picture" if kinds and all(k == "picture" for k in kinds) else "video"


def plan(mode: str, targets: list[dict]) -> list[dict]:
    """The prompts to make for a prompt mode and the idea's wires. `targets`: {id, kind: scene|picture, seconds, frame, flux}.
    Returns [{form: video|picture|frame, seconds, frame, targets: [ids]}]. "auto" (no mode picked) goes by the wiring:
    pictures only -> one picture prompt; scenes only or nothing -> one video prompt; both -> two, each with its own wires."""
    scenes = [t for t in targets if t.get("kind") == "scene"]
    pics = [t for t in targets if t.get("kind") == "picture"]
    sc = scenes[0] if scenes else None
    secs = float(sc.get("seconds") or 5) if sc else 5.0

    def video(ids):
        return {"form": "video", "seconds": secs, "frame": bool(sc and sc.get("frame")), "targets": ids}

    def picture(ids):
        # FLUX.2 Klein (drawn from reference pictures) has a form of its own; Krea 2 reads the text alone
        flux = any(t.get("flux") for t in pics)
        return {"form": "frame" if flux else "picture", "seconds": 5.0, "frame": False, "targets": ids}

    if mode == "auto":
        if scenes and pics:
            return [video([t["id"] for t in scenes]), picture([t["id"] for t in pics])]
        mode = default_mode([t.get("kind", "") for t in targets])
    if mode == "picture":
        return [picture([t["id"] for t in pics])]
    return [video([t["id"] for t in scenes])]


def render_script(d: dict) -> str:
    """The script's scenes as plain text for a note: «Сцена 1. Где: … Кто: … Что происходит: …»."""
    word, where, who, what = LABELS.get(i18n.text(), LABELS["en"])
    out = []
    title = str(d.get("title", "")).strip()
    if title:
        out.append(title)
        out.append("")
    for k, s in enumerate(d.get("scenes") or [], 1):
        out.append(f"{word} {k}.")
        for label, key in ((where, "where"), (who, "who"), (what, "what")):
            v = str(s.get(key, "")).strip()
            if v:
                out.append(f"{label}: {v}")
        out.append("")
    return "\n".join(out).strip()


async def make(mode: str, text: str, targets: list[dict], model_id: Optional[str] = None, video: Optional[str] = None,
               seed: int = 1) -> dict:
    """{mode, prompts: [{form, en, targets}]} for a prompt mode (mode "auto": by the wiring), {mode, note: {title, text}}
    for the script and the talk - those change nothing else in the graph."""
    text = text.strip()
    if mode in ("script", "think"):
        client.use_lang(i18n.text_name())
        async with client.session(model_id) as llm:
            if mode == "script":
                d = await llm.chat_json(SCRIPT_SYSTEM, text, SCRIPT_SCHEMA, temperature=0.7, seed=seed, max_tokens=3000, step="script")
                body = render_script(d)
                title = str(d.get("title", "")).strip()
            else:
                d = await llm.chat_json(THINK_SYSTEM, text, THINK_SCHEMA, temperature=0.7, seed=seed, max_tokens=3000, step="script")
                body = str(d.get("answer", "")).strip()
                title = ""
            if not body:
                raise client.LLMError(i18n.L("Сценарист не вернул ответа", "The writer returned nothing"))
            return {"mode": mode, "note": {"title": title, "text": body}, "model": llm.model.name}
    if mode not in PROMPT_MODES + ("auto",):
        raise client.LLMError(i18n.L("Неизвестный режим", "Unknown mode"))
    prompts = []
    model = ""
    for p in plan(mode, targets):
        target = "video" if p["form"] == "video" else p["form"]   # translate's own words: video | picture | frame
        r = await translate.translate(text, p["seconds"], model_id, seed, video=video, frame=p["frame"], target=target,
                                  extra=PICTURE_EXTRA if p["form"] != "video" else "")
        if not r.get("en"):
            raise client.LLMError(i18n.L("Сценарист не вернул перевода", "The writer returned no translation"))
        model = r.get("model", model)
        prompts.append({"form": p["form"], "en": r["en"], "targets": p["targets"]})
    return {"mode": mode, "prompts": prompts, "model": model}
