"""«Подача» and «Вид» instead of «Настроение» (2026-11-02).

A delivery (DELIVERIES) is how the video tells its story: a brief for the writer, the range of a scene's length, the
share of scenes without a face (inserts), the cameras it prefers. A look (LOOKS) is how the picture looks: a fragment
the video's style_en starts with, and the hero's rules - a live look bans the words that drew a doll («porcelain skin,
large expressive eyes with long lashes», a test clip of 2026-11-02) and adds anchors of a real person; the portrait's
framing; the singing scenes' camera; `face_tested` - whether LTX holds the face in it (None: not tested yet).
They combine freely. "auto" («Решит сценарист») in either: the writer picks one of the lists by the song or the idea
(decide), with a sentence why; the picked preset's rules apply as if chosen by hand.

The plan keeps: delivery, look ("auto" by default), look_own (the user's own words about the look), look_pick
({delivery, look, why_ru, why_en} when the writer decided), look_mine (a snapshot of a saved «Мой вид» when one is
chosen), looks_v (1: the plan is written by these rules - an older plan keeps its brief, word for word, and so its
answers in the LLM cache; 2: a look that `needs_frame` starts every scene from a picture drawn in it - needs_frame()).
An older plan's mood maps to a delivery (migrate). «Мои виды»: data/my_looks.json.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from pathlib import Path
from typing import Optional

from . import config, i18n

AUTO = "auto"
LOOKS_V = 2   # 2 (2026-11-03): a needs_frame look draws every scene's start frame (needs_frame)

# ---------------------------------------------------------------------------------------------------------------
# «Подача»: how the story is told
# ---------------------------------------------------------------------------------------------------------------
# id: (ru, en, hint_ru, hint_en, brief for the writer, (scene s min, max), inserts share, preferred cameras)
_D = [
    ("cinema", "Кино", "Cinema", "История с началом, поворотом и концом", "A story with a beginning, a turn and an ending",
     "cinematic live-action short film: a clear story with a beginning, a turn and an ending; the scenes flow like a film",
     (4, 8), 0.25, ("push_in", "track_side", "pan", "static")),
    ("clip", "Клип", "Music video", "Ритм, образы и исполнение под песню", "Rhythm, imagery and performance to the song",
     "music video: rhythmic, stylish, expressive motion; performance mixed with imagery that grows through the song",
     (2, 6), 0.5, ("orbit", "push_in", "track_side", "pan")),
    ("ad", "Реклама", "Ad", "Чисто, светло, с финальным кадром-героем", "Clean, bright, with a final hero shot",
     "polished commercial: a product or an idea shown clean, bright and aspirational, ending on a clear hero shot",
     (2, 5), 0.4, ("push_in", "orbit", "rise")),
    ("docu", "Документальное", "Documentary", "Наблюдение: настоящие места и свет", "Observation: real places and real light",
     "documentary: natural and observational, real places and available light, nothing staged or dramatic",
     (4, 10), 0.3, ("static", "pan", "follow", "track_side")),
    ("fairytale", "Сказка", "Fairy tale", "Простая волшебная история с моралью", "A simple magical story with a moral",
     "a fairy tale for grown-ups: a simple magical story with a gentle moral, wonder in every scene",
     (4, 8), 0.3, ("push_in", "rise", "pan", "orbit")),
    ("trailer", "Трейлер", "Trailer", "Короткие резкие кадры, напряжение растёт", "Short punchy shots, rising tension",
     "a film trailer: short punchy shots, tension rising scene by scene, the biggest moment held back to the end",
     (1.5, 4), 0.4, ("push_in", "pull_back", "orbit", "track_side")),
    ("vlog", "Влог", "Vlog", "Герой показывает свой день в камеру", "The hero shows their day to the camera",
     "a personal vlog: the hero shows their day straight to the camera, casual and direct, everyday places",
     (3, 8), 0.2, ("track_front", "static", "follow")),
    ("concert", "Концерт", "Concert", "Сцена, свет, дым, энергия шоу", "A stage, lights, haze, the energy of a show",
     "a live concert: the performer on a stage, beams of light and haze, the energy of the show; no audience faces",
     (2, 5), 0.2, ("orbit", "push_in", "rise", "pan")),
    ("dance", "Танцевальный", "Dance", "Движение тела и есть история", "The body's movement is the story",
     "a dance video: the body and its movement are the story, the camera moves with the dancer",
     (2, 5), 0.2, ("orbit", "track_side", "pull_back")),
    ("lyric", "Лирика (текст на экране)", "Lyric video (words on screen)", "Спокойные образы, место для слов песни",
     "Calm images that leave room for the song's words",
     "a lyric video: calm atmospheric images with empty space in the frame for the song's words added in editing; "
     "slow motion, few people", (4, 8), 0.6, ("static", "pan", "push_in")),
    ("nostalgia", "Ностальгия-хроника", "Nostalgic chronicle", "Моменты жизни, как старая домашняя хроника",
     "Moments of a life like old home movies",
     "a nostalgic chronicle: moments of a life like old home movies, one memory after another, warm and tender",
     (3, 6), 0.4, ("static", "pan", "push_in")),
    ("short", "Короткая история (Shorts)", "Short story (Shorts)", "Крючок в первые секунды, поворот, развязка",
     "A hook in the first seconds, a twist, a payoff",
     "a short vertical story: a hook in the first two seconds, one simple twist, a quick payoff",
     (2, 4), 0.2, ("push_in", "track_front", "static")),
    ("product", "Обзор товара", "Product review", "Вещь крупно, в деле, с разных сторон", "The thing close up, in use, from every side",
     "a product review: the thing in close details, in use and from several sides, in clean light",
     (2, 5), 0.6, ("orbit", "push_in", "static")),
    ("howto", "Обучение / инструкция", "How-to / tutorial", "Понятные шаги один за другим", "Clear steps one after another",
     "a how-to: clear steps one after another, the hands and the result well seen, calm steady shots",
     (4, 8), 0.4, ("static", "push_in")),
    ("meditative", "Медитативное", "Meditative", "Медленно, спокойно, природа и дыхание", "Slow, calm, nature and breath",
     "a meditative video: slow and calm, nature and breath, very little action, long held shots",
     (6, 10), 0.6, ("static", "push_in", "pan", "rise")),
    ("comedy", "Комедия", "Comedy", "Лёгкая ситуация со смешным поворотом", "A light situation with a funny turn",
     "a comedy: a light everyday situation with a funny turn, expressive faces, the timing of a sketch",
     (3, 6), 0.2, ("static", "push_in")),
    ("horror", "Хоррор", "Horror", "Страх нарастает медленно, темнота", "Dread built slowly, darkness",
     "a horror short: dread built slowly, darkness, something almost seen, a sudden scare at the end",
     (3, 7), 0.4, ("push_in", "pull_back", "static")),
    ("musical", "Мюзикл", "Musical", "Герой поёт и движется по сюжету", "The hero sings and moves through the story",
     "a musical: the hero sings and moves through the story, theatrical light, the song carries the plot",
     (3, 6), 0.3, ("orbit", "track_side", "rise")),
]
DELIVERIES: dict[str, dict] = {
    AUTO: {"id": AUTO, "ru": "Решит сценарист", "en": "Writer decides", "hint_ru": "Сценарист выберет по песне или идее",
           "hint_en": "The writer picks by the song or the idea", "brief": "", "scene": None, "inserts": None, "cameras": []},
    **{d[0]: {"id": d[0], "ru": d[1], "en": d[2], "hint_ru": d[3], "hint_en": d[4], "brief": d[5], "scene": d[6],
              "inserts": d[7], "cameras": list(d[8])} for d in _D},
}

# ---------------------------------------------------------------------------------------------------------------
# «Вид»: how the picture looks
# ---------------------------------------------------------------------------------------------------------------
GROUPS = [("live", "Живое", "Live"), ("anim", "Анимация", "Animation"), ("drawn", "Рисованное", "Drawn"),
          ("retro", "Ретро", "Retro"), ("genre", "Жанровое", "Genre"), ("art", "Арт", "Art")]
MINE = ("mine", "Мои", "Mine")

# the words that drew a doll in a live look (a test clip, 2026-11-02): cut from the hero's look, with their comma
BANNED = [r"porcelain(?:[- ]like)?(?:\s+(?:skin|complexion|face))?", r"doll[- ]?like(?:\s+\w+)?", r"dollish", r"\bdoll\b",
          r"barbie[- ]?like", r"flawless(?:\s+(?:skin|complexion|face))?", r"poreless(?:\s+skin)?", r"airbrushed(?:\s+skin)?",
          r"glass skin", r"perfectly smooth(?:\s+skin)?", r"(?:huge|large|big|enormous|oversized)\s+(?:\w+\s+){0,2}eyes",
          r"long(?:,?\s+(?:thick|dark|curled|fluttering|luscious))*\s+(?:eye)?lashes", r"thick(?:,?\s+\w+)?\s+(?:eye)?lashes",
          r"anime[- ]like(?:\s+\w+)?"]
_BANNED = re.compile(r"(?:,\s*|\b(?:and|with)\s+)?(?:\b(?:an?|the)\s+)?(?:" + "|".join(BANNED) + r")(?:\s+(?:and|with)\s+(?:" + "|".join(BANNED) + r"))?", re.I)
ANCHORS = "A real person: natural skin texture with fine pores, natural proportions, real features."
NONPERSON_PHOTO = {"animal": "Real photo, natural fur texture.", "robot": "Real photo, natural materials and reflections."}   # rules_v 4
WOMAN_PHOTO = "Photo of a real woman, natural skin texture."
MAN_PHOTO = "Photo of a real man, natural skin texture."
LIVE_RULE = ("A woman's look reads clearly feminine and attractive, a man's clearly masculine - and always a real person: "
             "name real features (the age, the shape of the face, the nose, the brows, a mole or freckles, skin with "
             "texture), never porcelain, doll-like, flawless skin, huge or large eyes, long lashes. The look starts with "
             "the build or the face: never with a name, a role or a label (\"Singer - ...\").")
# A plan written since rules_v 2 (2026-11-03, the owner: «без указания женственная и красивая», «пусть будет гибко»): no
# words about how feminine or attractive anyone looks - the idea's words decide; the real-person anchors stay
LIVE_RULE_V2 = ("Always a real person: name real features (the age, the shape of the face, the nose, the brows, a mole or "
                "freckles, skin with texture), never porcelain, doll-like, flawless skin, huge or large eyes, long lashes. "
                "The look starts with the build or the face: never with a name, a role or a label (\"Singer - ...\").")

# id, group, ru, en, hint_ru, hint_en, style_en fragment, live, medium (the portrait's), portrait framing, singing
# camera (None: the caller's default), tint (the tile's placeholder: two colours)
_L = [
    ("live_cinema", "live", "Живое кино", "Live cinema", "Настоящие люди, мягкий свет кино", "Real people, soft film light",
     "live-action cinematic film, natural light, shallow depth of field, subtle film grain", True, "photo", "waist-up", None, ("#3a2f4a", "#d9a35b")),
    ("docu_photo", "live", "Документальное фото", "Documentary photo", "Живой свет, как в репортаже", "Available light, like a reportage",
     "documentary photography look, available light, natural colours, candid framing, 35mm lens", True, "photo", "waist-up", None, ("#3d4a3a", "#9aa58a")),
    ("glossy", "live", "Глянец", "Glossy", "Журнальный студийный свет", "Magazine studio light",
     "glossy fashion-magazine look, soft studio light, rich clean colours, crisp detail", True, "photo", "waist-up", None, ("#f0c6e0", "#e04c8a")),
    ("night_neon", "live", "Ночной неон", "Night neon", "Город ночью, отражения неона", "A city at night, neon reflections",
     "live-action night city, neon light in magenta and cyan reflecting on wet streets", True, "photo", "waist-up", None, ("#120f2e", "#e0307a")),
    ("golden_hour", "live", "Золотой час", "Golden hour", "Тёплое низкое солнце", "Warm low sun",
     "live-action golden hour, warm low sun, long soft shadows, glowing backlight", True, "photo", "waist-up", None, ("#e0703a", "#f6c46a")),
    ("rainy_city", "live", "Дождливый город", "Rainy city", "Пасмурно, дождь, отражения", "Overcast, rain, reflections",
     "live-action rainy city, overcast light, rain streaks and reflections, muted blue-grey palette", True, "photo", "waist-up", None, ("#2e3a48", "#7d8b99")),
    ("anime", "anim", "Аниме", "Anime", "Чистые линии, яркие цвета", "Clean lines, vivid colours",
     "anime style, cel-shaded animation, clean line art, vivid colours, painted backgrounds", False, "anime illustration", "medium close-up", "push_in", ("#3f6fd8", "#9ad0ff")),
    ("cartoon3d", "anim", "3D-мультфильм", "3D cartoon", "Мягкие формы, тёплый свет", "Soft shapes, warm light",
     "3D animated film style, soft rounded shapes, expressive stylised characters, warm global illumination", False, "3D render", "medium close-up", "push_in", ("#f06a7a", "#5aa0f0")),
    ("clay", "anim", "Пластилин", "Claymation", "Фигурки из пластилина", "Plasticine figures",
     "claymation, handmade plasticine figures with visible fingerprints, soft studio light", False, "claymation still", "medium close-up", "push_in", ("#f08a5a", "#f6d06a")),
    ("stopmotion", "anim", "Стоп-моушен", "Stop-motion", "Миниатюрные декорации", "Miniature sets",
     "stop-motion animation, miniature handmade sets, felt and wood textures, slight frame jitter", False, "stop-motion still", "medium close-up", "push_in", ("#8a6a4a", "#c9a46a")),
    ("papercut", "anim", "Бумажная аппликация", "Paper cut-out", "Слои цветной бумаги", "Layers of coloured paper",
     "paper cut-out animation, layered coloured paper, visible paper texture, soft shadows between layers", False, "paper cut-out illustration", "medium close-up", "push_in", ("#3a8a6a", "#e8d6a0")),
    ("game", "anim", "Игровая графика", "Game graphics", "Как в видеоигре", "Like a video game",
     "video game graphics style, real-time 3D render, stylised textures, dramatic game lighting", False, "3D render", "medium close-up", "push_in", ("#2a4aa8", "#3aa84a")),
    ("watercolor", "drawn", "Акварель", "Watercolour", "Мягкие размывы на бумаге", "Soft washes on paper",
     "watercolour illustration, soft bleeding washes, paper texture, light pastel palette", False, "watercolour illustration", "medium close-up", "push_in", ("#a8c8e8", "#e8b0c8")),
    ("oil", "drawn", "Масло", "Oil painting", "Мазки, классический свет", "Brush strokes, classical light",
     "oil painting illustration, visible brush strokes, rich impasto texture, classical warm light", False, "oil painting", "medium close-up", "push_in", ("#4a3a28", "#c8a050")),
    ("comic", "drawn", "Комикс", "Comic", "Контур, растр, яркие цвета", "Outlines, halftone, bright colours",
     "comic book illustration, bold ink outlines, halftone shading, saturated flat colours", False, "comic illustration", "medium close-up", "push_in", ("#f04a3a", "#f6d03a")),
    ("manga_bw", "drawn", "Манга ч/б", "B&W manga", "Тушь и скринтон", "Ink and screentone",
     "black and white manga illustration, ink lines, screentone shading, high contrast", False, "manga illustration", "medium close-up", "push_in", ("#f2f2f2", "#303030")),
    ("sketch", "drawn", "Карандашный скетч", "Pencil sketch", "Графит, штриховка", "Graphite, hatching",
     "pencil sketch illustration, graphite lines, cross-hatching, off-white paper", False, "pencil drawing", "medium close-up", "push_in", ("#e8e4dc", "#7a7670")),
    ("pastel", "drawn", "Пастель", "Pastel", "Мелок, мягкие цвета", "Chalk, soft colours",
     "soft pastel illustration, chalky texture, gentle muted colours, dreamy light", False, "pastel illustration", "medium close-up", "push_in", ("#f0c8d8", "#b8d0f0")),
    ("retro_film", "retro", "Ретро-плёнка", "Retro film", "Тёплые выцветшие цвета, зерно", "Warm faded colours, grain",
     "1970s film look, warm faded colours, heavy film grain, soft halation", True, "photo", "waist-up", None, ("#8a5a3a", "#e8b070")),
    ("vhs90", "retro", "VHS 90-х", "90s VHS", "Домашняя кассета: шум, полосы", "A home tape: noise, scan lines",
     "1990s VHS home video look, soft focus, colour bleeding, scan lines, tape noise", True, "photo", "waist-up", None, ("#2a2a4a", "#e05ab0")),
    ("synthwave", "retro", "Синтвейв", "Synthwave", "Неон 80-х, пурпурная дымка", "80s neon, purple haze",
     "synthwave 1980s look, magenta and cyan neon light, purple haze, retro-futuristic glow", True, "photo", "waist-up", None, ("#2a0a4a", "#f0508a")),
    ("noir", "retro", "Нуар", "Noir", "Ч/б, жёсткие тени", "B&W, hard shadows",
     "black and white film noir, hard low-key light, deep shadows, light through blinds", True, "black and white photo", "waist-up", None, ("#101010", "#c8c8c8")),
    ("silent", "retro", "Немое кино", "Silent film", "1920-е, мерцание, виньетка", "The 1920s, flicker, vignette",
     "silent film look, black and white 1920s footage, flickering exposure, soft vignette", True, "black and white photo", "waist-up", None, ("#3a3630", "#d8d0c0")),
    ("polaroid", "retro", "Полароид", "Instant photo", "Мгновенное фото, засветы", "An instant photo, light leaks",
     "instant film photo look, washed warm colours, soft contrast, slight light leaks", True, "photo", "waist-up", None, ("#e8dcc0", "#e07a4a")),
    ("cyberpunk", "genre", "Киберпанк", "Cyberpunk", "Город будущего под дождём", "A future city in the rain",
     "live-action cyberpunk, rain-soaked futuristic city, neon light, high-tech grit", True, "photo", "waist-up", None, ("#0a1030", "#30d0e0")),
    ("fantasy_epic", "genre", "Фэнтези-эпик", "Epic fantasy", "Магия и масштаб, фотореализм", "Magic and scale, photoreal",
     "photoreal epic fantasy with visual effects, grand landscapes, magical light, cinematic scale", True, "photo", "waist-up", None, ("#3a2a5a", "#e8c070")),
    ("horror_mood", "genre", "Хоррор-атмосфера", "Horror mood", "Холод, туман, тени", "Cold, fog, shadows",
     "live-action horror atmosphere, cold dim light, fog, deep shadows, desaturated colours", True, "photo", "waist-up", None, ("#101a18", "#5a7a6a")),
    ("space", "genre", "Космос", "Space", "Звёзды, корабли, холодный свет", "Stars, ships, cold light",
     "live-action science fiction in space, starfields, spacecraft interiors, cold blue light", True, "photo", "waist-up", None, ("#05051a", "#7a6af0")),
    ("postapoc", "genre", "Постапокалипсис", "Post-apocalypse", "Руины, пыль, жёсткое солнце", "Ruins, dust, harsh sun",
     "live-action post-apocalyptic world, ruins, dust, harsh sun, bleached colours", True, "photo", "waist-up", None, ("#5a4028", "#d8a060")),
    ("fairy_forest", "genre", "Сказочный лес", "Enchanted forest", "Мох, туман, волшебный свет", "Moss, mist, magical light",
     "photoreal enchanted forest, glowing particles, moss, soft magical light through mist", True, "photo", "waist-up", None, ("#0a3020", "#7ad08a")),
    ("pixel", "art", "Пиксель-арт", "Pixel art", "Крупные пиксели, мало цветов", "Big pixels, few colours",
     "pixel art illustration, limited palette, crisp square pixels, retro game look", False, "pixel art illustration", "medium close-up", "push_in", ("#3aa0e0", "#50c050")),
    ("lofi", "art", "Лоу-фай", "Lo-fi", "Уютно, приглушённо, вечер", "Cosy, muted, evening",
     "lo-fi illustration, cosy muted colours, soft grain, calm evening light", False, "lo-fi illustration", "medium close-up", "push_in", ("#3a3058", "#d0a070")),
    ("stained_glass", "art", "Витраж", "Stained glass", "Свет сквозь цветное стекло", "Light through coloured glass",
     "stained glass illustration, bold lead lines, glowing jewel colours, light shining through", False, "stained glass illustration", "medium close-up", "push_in", ("#c02a4a", "#2a6ac0")),
    ("neon_lines", "art", "Неоновые линии", "Neon lines", "Светящиеся контуры на тёмном", "Glowing outlines on dark",
     "neon line art illustration, glowing outlines on a dark background, minimal shapes", False, "neon line illustration", "medium close-up", "push_in", ("#0a0a14", "#f040c0")),
    ("minimal", "art", "Минимализм", "Minimalism", "Пустое пространство, мало предметов", "Empty space, few objects",
     "minimalist live-action look, clean empty spaces, few objects, soft even light, muted palette", True, "photo", "waist-up", None, ("#ecebe6", "#d04a5a")),
    ("surreal", "art", "Сюрреализм", "Surrealism", "Невозможные сцены, как во сне", "Impossible scenes, like a dream",
     "photoreal surrealism, dreamlike impossible scenes, soft light, strange scale", True, "photo", "waist-up", None, ("#e0a0c0", "#6040a0")),
]
LOOKS: dict[str, dict] = {
    AUTO: {"id": AUTO, "group": AUTO, "ru": "Решит сценарист", "en": "Writer decides", "hint_ru": "Сценарист выберет вид из списка",
           "hint_en": "The writer picks a look from the list", "style_en": "", "live": True, "medium": "photo",
           "portrait": "waist-up", "sing_camera": None, "face_tested": None, "tint": ("#5a2a8a", "#d040a0")},
    **{x[0]: {"id": x[0], "group": x[1], "ru": x[2], "en": x[3], "hint_ru": x[4], "hint_en": x[5], "style_en": x[6], "live": x[7],
              "medium": x[8], "portrait": x[9], "sing_camera": x[10], "face_tested": None, "tint": x[11]} for x in _L},
}
FALLBACK_LOOK = "live_cinema"

# Drawn by every frame (hidden looks tried by two routes, 2026-11-03): from text LTX 2.5 turned these into a
# live photo; a still drawn in the look, then image-to-video from it with the motion and one phrase of the technique as
# the prompt, held the look for the whole 5 s. id -> (the frame's medium, said strongly - frames.py, places.py; the
# technique's phrase after the motion - planner.prompts, model_prompts). Style LoRAs on LTX 2.3 did not hold (a 3D doll
# instead of the style): not used.
FRAME_LOOKS = {
    "watercolor": ("A watercolour painting on textured paper, not a photograph: the people and the place are painted in "
                   "soft bleeding washes.", "Watercolour animation."),
    "oil": ("An oil painting on canvas, not a photograph: the people and the place are painted with visible brush "
            "strokes.", "Oil painting in motion."),
    "comic": ("A comic book panel, not a photograph: the people and the place are inked with bold outlines, halftone "
              "shading and flat colours.", "Comic book animation."),
    "sketch": ("A pencil drawing on off-white paper, not a photograph: the people and the place are drawn in graphite "
               "lines and cross-hatching.", "Pencil sketch animation."),
    "clay": ("A claymation still, not a photograph: the people are handmade plasticine figures with visible "
             "fingerprints in a handmade miniature set.", "Claymation, plasticine figure."),
    "stopmotion": ("A stop-motion animation still, not a photograph: the people are handmade puppets in a miniature set "
                   "of felt and wood.", "Stop-motion animation."),
}
for _k, (_medium, _tech) in FRAME_LOOKS.items():
    LOOKS[_k].update(needs_frame=True, frame_en=_medium, tech_en=_tech)

# Not offered: LTX 2.5 drew a live photo from these by text alone (108 samples, 2026-11-03, the look trials) and they have no frame route (FRAME_LOOKS). They stay in LOOKS, so a stored plan with one keeps working.
# Paper cut-out from a frame came out flat vector, pixel art more a drawing than pixels (the same tests).
HIDDEN = frozenset({"game", "pastel", "retro_film", "vhs90", "polaroid", "pixel", "lofi", "stained_glass", "neon_lines",
                    "minimal", "surreal"})
# H3 held these by text on a close-up (the same samples), LTX did not: offered only when H3 shoots the video. Comic
# has a frame route now and is offered for every model.
H3_ONLY = frozenset({"papercut"})


def offered(video: Optional[str] = None) -> list[dict]:
    """The looks the page and the writer choose from (no «Решит сценарист», no hidden ones). `video`: the model that
    shoots - not H3 leaves out H3_ONLY; None: all of them (the page filters by its model)."""
    return [x for x in LOOKS.values() if x["id"] != AUTO and x["id"] not in HIDDEN
            and (video in (None, "h3") or x["id"] not in H3_ONLY)]

# «Настроение» of older plans: the chip (settings.mood) or the phrase the writer got (plan.mood) -> (delivery, look)
MOOD_MAP = {
    "Кино": ("cinema", AUTO), "cinematic live-action film": ("cinema", AUTO),
    "Клип": ("clip", AUTO), "music video: rhythmic, stylish, expressive motion": ("clip", AUTO),
    "Реклама": ("ad", AUTO), "polished commercial: clean, bright, aspirational": ("ad", AUTO),
    "Документальное": ("docu", AUTO), "documentary: natural, observational, handheld feel": ("docu", AUTO),
    "Фэнтези и эффекты": ("cinema", "fantasy_epic"), "epic fantasy with visual effects, photoreal": ("cinema", "fantasy_epic"),
}


def name(x: dict) -> str:
    return i18n.L(x["ru"], x["en"])


def hint(x: dict) -> str:
    return i18n.L(x["hint_ru"], x["hint_en"])


# ---------------------------------------------------------------------------------------------------------------
# «Мои виды»: data/my_looks.json - [{id, name, base, own}]
# ---------------------------------------------------------------------------------------------------------------
MY_FILE = config.DATA_DIR / "my_looks.json"
PREVIEWS = config.DATA_DIR / "looks"          # the studio's own drawn tiles (data/looks/<id>.jpg), win over the shipped ones
TILES = Path(__file__).resolve().parent / "looks_tiles"   # shipped tiles (<id>.webp), made by tools/make_look_tiles.py
_lock = threading.Lock()


def my_looks() -> list[dict]:
    try:
        got = json.loads(MY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [x for x in got if isinstance(x, dict) and isinstance(x.get("id"), str) and x.get("base") in LOOKS] if isinstance(got, list) else []


def _save_mine(items: list[dict]) -> None:
    MY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = MY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(MY_FILE)


def _check_mine(name_: str, base: str, own: str) -> dict:
    name_, own = (name_ or "").strip()[:60], (own or "").strip()[:600]
    if not name_:
        raise ValueError(i18n.L("Назовите свой вид", "Name your look"))
    if base not in LOOKS:
        raise ValueError(i18n.L("Неизвестный вид", "Unknown look"))
    return {"name": name_, "base": base, "own": own}


def add_mine(name_: str, base: str, own: str) -> dict:
    with _lock:
        x = {"id": f"my_{uuid.uuid4().hex[:8]}", **_check_mine(name_, base, own)}
        _save_mine(my_looks() + [x])
        return x


def edit_mine(lid: str, name_: str, base: str, own: str) -> dict:
    with _lock:
        items = my_looks()
        x = next((i for i in items if i["id"] == lid), None)
        if x is None:
            raise KeyError(lid)
        x.update(_check_mine(name_, base, own))
        _save_mine(items)
        return x


def remove_mine(lid: str) -> None:
    with _lock:
        items = my_looks()
        if not any(i["id"] == lid for i in items):
            raise KeyError(lid)
        _save_mine([i for i in items if i["id"] != lid])


def mine_of(lid: str) -> Optional[dict]:
    return next((x for x in my_looks() if x["id"] == lid), None)


def preview_path(lid: str):
    """data/looks/<id>.jpg when the studio drew it, else the shipped app/looks_tiles/<id>.webp, else None."""
    if lid not in LOOKS and not mine_of(lid):
        return None
    for p in (PREVIEWS / f"{lid}.jpg", TILES / f"{lid}.webp"):
        if p.exists():
            return p
    return None


def public() -> dict:
    """GET /api/looks: the lists in the interface's language."""
    return {
        "deliveries": [{"id": d["id"], "name": name(d), "hint": hint(d), "scene": d["scene"], "inserts": d["inserts"]} for d in DELIVERIES.values()],
        "groups": [{"id": g, "name": i18n.L(ru, en)} for g, ru, en in GROUPS if any(x["group"] == g for x in offered())]
                  + [{"id": MINE[0], "name": i18n.L(MINE[1], MINE[2])}],
        "looks": [{"id": x["id"], "group": x["group"], "name": name(x), "hint": hint(x), "live": x["live"], "tint": list(x["tint"]),
                   "face_tested": x["face_tested"], "preview": bool(preview_path(x["id"])),
                   "models": ["h3"] if x["id"] in H3_ONLY else None, "needs_frame": bool(x.get("needs_frame"))}
                  for x in (LOOKS[AUTO], *offered())],
        "hidden": [{"id": x, "name": name(LOOKS[x])} for x in sorted(HIDDEN)],   # a stored plan's look still has a name
        "mine": [{**x, "group": MINE[0], "preview": bool(preview_path(x["id"]))} for x in my_looks()],
    }


# ---------------------------------------------------------------------------------------------------------------
# a plan's delivery and look
# ---------------------------------------------------------------------------------------------------------------
def migrate(plan: dict, mood_key: str = "") -> bool:
    """An older plan (no `delivery`): its mood -> delivery (and look); a clip without one - «Клип». -> changed."""
    if not isinstance(plan, dict) or "delivery" in plan:
        return False
    d, lk = MOOD_MAP.get(mood_key) or MOOD_MAP.get(str(plan.get("mood") or "").strip()) or (("clip", AUTO) if plan.get("clip") else (AUTO, AUTO))
    plan["delivery"], plan["look"] = d, plan.get("look") if plan.get("look") in LOOKS else lk
    plan.setdefault("look_own", "")
    return True


def choose(plan: dict, delivery: Optional[str] = None, look: Optional[str] = None, own: Optional[str] = None) -> dict:
    """The user's choice into the plan (a new one, or a change): unknown ids are "auto"; a saved look («Мой вид») is
    kept as a snapshot (look_mine). A concrete choice drops the writer's pick of that row."""
    if delivery is not None:
        plan["delivery"] = delivery if delivery in DELIVERIES else AUTO
    if look is not None:
        # a saved look deleted since: the snapshot the plan keeps stands for it
        m = (mine_of(look) or (plan.get("look_mine") if plan.get("look") == look else None)) if look.startswith("my_") else None
        plan["look"] = look if look in LOOKS or m else AUTO
        if m:
            plan["look_mine"] = {"name": m["name"], "base": m["base"], "own": m["own"]}
        else:
            plan.pop("look_mine", None)
    if own is not None:
        plan["look_own"] = own.strip()[:600]
    plan.setdefault("delivery", AUTO)
    plan.setdefault("look", AUTO)
    plan.setdefault("look_own", "")
    pick = plan.get("look_pick")
    if pick and plan["delivery"] != AUTO and plan["look"] != AUTO:
        plan.pop("look_pick")
    plan["looks_v"] = LOOKS_V
    return plan


KEYS = ("delivery", "look", "look_own", "look_mine", "look_pick", "looks_v")


def choose_request(plan: dict, delivery: str = "", look: str = "", own: str = "", mood: str = "") -> dict:
    """A new plan's choice from a request: an older client sends only «Настроение» - mapped (MOOD_MAP)."""
    if not delivery and mood:
        d, lk = MOOD_MAP.get(mood, (AUTO, AUTO))
        delivery, look = d, look or lk
    return choose(plan, delivery or AUTO, look or AUTO, own or "")


def active(plan: dict) -> bool:
    """The plan is written by these rules (a new one, or its look changed since)."""
    return bool(plan.get("looks_v"))


def fallback(plan: dict) -> tuple[str, str]:
    """«Решит сценарист» when the writer can't: a clip or a song -> a music video, else cinema; live cinema."""
    return ("clip" if plan.get("clip") else "cinema"), FALLBACK_LOOK


def resolve(plan: dict) -> tuple[str, str]:
    """(delivery id, look id) in effect: the user's, else the writer's pick, else the fallback. A saved look -> its base."""
    p = dict(plan)
    migrate(p)
    pick = p.get("look_pick") or {}
    fd, fl = fallback(p)
    d = p.get("delivery") if p.get("delivery") in DELIVERIES and p.get("delivery") != AUTO else pick.get("delivery") if pick.get("delivery") in DELIVERIES and pick.get("delivery") != AUTO else fd
    lk = p.get("look") or AUTO
    if lk.startswith("my_"):
        lk = (p.get("look_mine") or mine_of(lk) or {}).get("base") or AUTO
    if lk not in LOOKS or lk == AUTO:
        lk = pick.get("look") if pick.get("look") in LOOKS and pick.get("look") != AUTO else fl
    return d, lk


def delivery_of(plan: dict) -> dict:
    return DELIVERIES[resolve(plan)[0]]


def look_of(plan: dict) -> dict:
    return LOOKS[resolve(plan)[1]]


def own_text(plan: dict) -> str:
    """The user's own words about the look: a saved look's and this plan's."""
    m = plan.get("look_mine") if str(plan.get("look") or "").startswith("my_") else None
    return " ".join(x for x in ((m or {}).get("own", ""), plan.get("look_own", "")) if x and x.strip()).strip()


def is_live(plan: dict) -> bool:
    return bool(look_of(plan)["live"])


def needs_frame(plan: dict) -> bool:
    """The look in effect is drawn by every frame (FRAME_LOOKS) and the plan was written since looks_v 2: every new scene
    starts from a picture drawn in the look (frames.can_draw), the places are painted in it (places.prompt_of), and a
    scene shot from its picture gets the motion and the technique's phrase only (tech). An older plan: its frames and
    prompts as they were, word for word."""
    return int((plan or {}).get("looks_v") or 0) >= 2 and bool(look_of(plan).get("needs_frame"))


def frame_medium(plan: dict) -> str:
    """The frame's medium said strongly, in place of «Photorealistic film still» ("" unless needs_frame)."""
    return look_of(plan)["frame_en"] if needs_frame(plan) else ""


# rules_v 4: a stylised look (not live, not retro film) holds its medium through the whole chain of image-to-video scenes
# (2026-11-03, a 3D-cartoon kitten story turned photoreal by its last scene): every scene says the medium again, and the
# photographic words (grain, lens, pores) are left out of its style and of the heroes' looks.
MEDIUM_ANCHOR = {   # family -> (the look's name, how it shows)
    "3D animated film": ("3D animated film look", "stylised shapes and surfaces, not photorealistic"),
    "anime": ("anime look", "cel shading and clean line art, not photorealistic"),
    "clay": ("claymation look", "handmade plasticine figures, not photorealistic"),
    "stopmotion": ("stop-motion look", "handmade puppets and miniature sets, not photorealistic"),
    "paper": ("paper cut-out look", "layered coloured paper, not photorealistic"),
    "game": ("stylised game-graphics look", "not photorealistic"),
    "drawn": ("hand-drawn look", "visible strokes and flat stylised colour, not a photograph"),
}
_ANCHOR_OF = {"cartoon3d": "3D animated film", "anime": "anime", "clay": "clay", "stopmotion": "stopmotion", "papercut": "paper", "game": "game"}


def stylised(plan: dict) -> bool:
    """A plan of rules_v 4 whose look is drawn or animated (not live action, not a retro film look)."""
    if int((plan or {}).get("rules_v") or 0) < 4 or not active(plan):
        return False
    lk = look_of(plan)
    return not lk["live"] and lk["group"] in ("anim", "drawn")


def medium_anchor(plan: dict) -> str:
    """«Keep the 3D animated film look of <Picture 1>: ...» - the short anchor each scene of a stylised look ends with."""
    if not stylised(plan) or needs_frame(plan):
        return ""
    lk = resolve(plan)[1]
    name, how = MEDIUM_ANCHOR[_ANCHOR_OF.get(lk, "drawn")]
    return f"Keep the {name} of <Picture 1>: {how}."


_PHOTO_WORDS = re.compile(r"(?:\s*[,;])?\s*\b(?:(?:fine|subtle|light|heavy|visible)\s+)?(?:film\s+)?grain(?:\s+texture)?\b"
                          r"|(?:\s*[,;])?\s*\b(?:shot (?:with|on) )?(?:a )?(?:\d+\s?mm|wide|anamorphic)(?: lens)?\b"
                          r"|(?:\s*[,;])?\s*\b(?:skin (?:with (?:visible )?)?texture|natural skin texture|(?:fine|visible) pores|pores)\b"
                          r"|\s*A real person:[^.]*\.|(?:\s*[,;])?\s*natural proportions, real features", re.I)


# rules_v 5: any adjective in front of grain goes with it («gentle film grain» left a dangling «gentle»)
_GRAIN_ADJ = re.compile(r"(?:\s*[,;])?\s*\b(?:(?:gentle|soft|slight|faint|natural|light|fine|subtle|heavy|visible|coarse|rich|"
                        r"warm|organic|delicate|gritty|a touch of|a little|some)\s+)+(?:film\s+)?grain(?:\s+texture)?\b", re.I)


def unphoto(text: str, v5: bool = False) -> str:
    """The photographic words (film grain, a 35 mm lens, skin texture, pores) out of a style or a hero's look."""
    out = re.sub(r"\bskin (?:with (?:visible )?)?texture\b", "skin", text or "", flags=re.I)
    if v5:
        out = _GRAIN_ADJ.sub("", out)
    out = _PHOTO_WORDS.sub("", out)
    out = re.sub(r"\s+([,.;])", r"\1", out)
    out = re.sub(r"([,;])\s*([,.;])", r"\2", out)
    return re.sub(r"\s{2,}", " ", out).strip(" ,;")


# Clearly photographic wording in a hand-written prompt (a drawn look cannot hold it): the text itself says «photo»
_PHOTO_CLAIMS = re.compile(r"(?:\s*[,;])?\s*\b(?:(?:extremely |highly |ultra[- ])?photo-?realistic(?: quality)?|photographic(?: quality)?|real photo(?:graph)?|"
                           r"(?:shallow |deep )?depth of field|bokeh(?: background)?|dslr)\b", re.I)


def unphoto_text(text: str) -> str:
    """unphoto plus the claims a hand-written prompt makes of a photograph (photorealistic, depth of field, bokeh); the
    composition and camera words stay."""
    # line by line: the prompt's paragraphs (Scene: / Camera: / Timeline:) stay apart
    lines = [unphoto(_PHOTO_CLAIMS.sub("", ln), True) for ln in (text or "").split("\n")]
    return "\n".join(lines).strip()


def drawn_of(look_id: Optional[str]) -> bool:
    """A look that is not live action: animated, drawn or an art look (pixel art, stained glass, neon lines)."""
    lk = LOOKS.get(look_id or "")
    return bool(lk) and not lk["live"]


def frame_look(look_id: Optional[str]) -> bool:
    """A look every frame of which is drawn (FRAME_LOOKS)."""
    return look_id in FRAME_LOOKS


def tech(plan: dict) -> str:
    """The technique's phrase after a scene's motion, when it is shot from its picture ("" unless needs_frame)."""
    return look_of(plan)["tech_en"] if needs_frame(plan) else ""


def state(plan: dict) -> dict:
    """What the interface shows: the choice, what is in effect, the writer's pick."""
    p = dict(plan or {})
    migrate(p)
    d, lk = resolve(p)
    return {"delivery": p.get("delivery", AUTO), "look": p.get("look", AUTO), "look_own": p.get("look_own", ""),
            "look_pick": p.get("look_pick"), "look_mine": p.get("look_mine"), "effective": {"delivery": d, "look": lk}}


# ---------------------------------------------------------------------------------------------------------------
# what the rules do
# ---------------------------------------------------------------------------------------------------------------
_STYLE_MAX = 46   # words: prompts.style_problems allows 50


# the writer's «anamorphic lens flares» (night_neon, 2026-11-03): LTX 2.5 shot an empty station letterboxed - black
# bars top and bottom inside the shot; videomodels.adapt's «widescreen lens» in its place still reads as a wide format
_ANAMORPHIC = re.compile(r"\banamorphic\s+", re.I)
_WIDE = re.compile(r"\s*\b(?:widescreen|letterbox(?:ed)?|cinemascope|2[.,]3[59]\s*:\s*1)\b(?:\s+(?:format|frame|aspect))?,?", re.I)


def no_letterbox(text: str) -> str:
    """The words that make a video model draw black bars, out (anamorphic lens flares -> lens flares)."""
    text = re.sub(r"\b([Aa])n\s+anamorphic\s+", r"\1 ", text or "")   # «an anamorphic lens» -> «a lens», not «an lens»
    return re.sub(r"\s{2,}", " ", _WIDE.sub("", _ANAMORPHIC.sub("", text))).strip()


# A model's or tool's name in the style («Shot on LTX-2.5», 2026-11-03: the writer copied it from the brief's model
# note): the video model reads it as words to draw. Only a plan of rules_v 3 (writer.RULES_V) is cleaned.
_TOOL = (r"(?:minimax(?:\s+hailuo)?(?:\s+h3)?|hailuo|lightricks|ltx(?:[\s-]?video)?|h3|wan(?:[\s-]?2\.\d)?(?:\s*5b)?|krea(?:\s*2)?|"
         r"flux(?:\.\d)?|klein|comfy\s?ui|stable\s+diffusion|gemma|qwen|mistral)")
_TOOL_VER = r"(?:[\s-]?v?\d+(?:\.\d+)*[a-z]?\b)?"
_SHOT_ON = re.compile(r"\b(?:shot|filmed|made|rendered|generated|created|produced)\s+(?:on|with|by|in|using)\s+" + _TOOL + _TOOL_VER
                      + r"(?:\s+(?:model|video\s+model|engine))?", re.I)
_TOOL_NAME = re.compile(r"\b" + _TOOL + _TOOL_VER + r"(?:\s+(?:model|video\s+model|engine))?(?![\w.-])", re.I)


def no_tools(text: str) -> str:
    """Model and tool names («Shot on LTX-2.5», «H3 look») out of a style; «shot on 35mm film» stays."""
    out = _TOOL_NAME.sub("", _SHOT_ON.sub("", text or ""))
    out = re.sub(r"\s+([,.;])", r"\1", out)
    out = re.sub(r"([,;])(?:\s*[,;])+", r"\1", out)
    out = re.sub(r"^[\s,;.]+", "", out)
    return re.sub(r"\s{2,}", " ", out).strip()


def style_for(plan: dict, rest: str = "") -> str:
    """style_en: the look's fragment first, then the writer's words for this video (`rest`), cut to fit. The fragment
    used is kept (look_style) so a change of look swaps it (restyle)."""
    frag = look_of(plan)["style_en"]
    rest = (rest or "").strip()
    old = plan.get("look_style") or ""
    if old and rest.lower().startswith(old.lower()):
        rest = rest[len(old):]
    if frag and rest.lower().startswith(frag.lower()):
        rest = rest[len(frag):]
    if plan.get("rules_v"):   # a plan written since 2026-11-03 (writer.RULES_V): no widescreen words, older plans as they were
        rest = no_letterbox(rest)
    if int(plan.get("rules_v") or 0) >= 3:   # rules_v 3: no model or tool names
        rest = no_tools(rest)
    rest = rest.strip(" ,.;")
    words = rest.split()
    room = _STYLE_MAX - len(frag.split())
    if len(words) > room:
        rest = " ".join(words[:max(0, room)]).rstrip(" ,;")
    plan["look_style"] = frag
    return ", ".join(x for x in (frag, rest) if x).strip() + ("." if frag or rest else "")


def clean_look(text: str, look: dict) -> str:
    """A hero's look (cast en) by the look's rules: a live look loses the words that draw a doll and gets the anchors
    of a real person (once); a drawn or animated one stays as it is."""
    if not look.get("live") or not text:
        return text
    out = _BANNED.sub("", text)
    out = re.sub(r"\s+,", ",", out)
    out = re.sub(r",\s*,+", ",", out)
    out = re.sub(r"\b(with|and)\s*([,.])", r"\2", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" ,")
    out = re.sub(r",\s*\.", ".", out)
    if ANCHORS.lower() not in out.lower():
        out = out.rstrip(" .") + ". " + ANCHORS
    return out


def has_banned(text: str) -> bool:
    return bool(_BANNED.search(text or ""))


# The owner's rule (2026-11-06): no drug hints in a clip's titles, HUD text, hashtags and publication text («кислота»,
# acid, trip...). A separate list from BANNED (that one keeps a hero from looking like a doll). It is for the words the
# STUDIO writes - a title, a HUD line, the post; the words of the song are sung as they are and never go through it, and
# a picture's colour («acid-green» in a style line) is not a title.
DRUG_HINTS = [r"кислот\w*", r"acid\w*", r"trip(?:s|py|ping|ped)?", r"трип\w*", r"lsd", r"лсд", r"molly", r"молли", r"mdma", r"мдма",
              r"экстази", r"ecstasy", r"extasy", r"эйфори\w*", r"psychedel\w*", r"психодел\w*", r"наркот\w*", r"narcotic\w*",
              r"drugs?", r"кокаин\w*", r"cocaine", r"героин\w*", r"heroin", r"марихуан\w*", r"marijuana", r"weed", r"травк\w*",
              r"шишк\w*", r"shrooms?", r"грибочк\w*", r"amphetamine\w*", r"амфетамин\w*", r"meth", r"ketamine", r"кетамин\w*",
              r"cannabis", r"каннабис\w*", r"hallucinogen\w*", r"галлюциноген\w*", r"overdose", r"передоз\w*", r"stoned", r"high on"]
_DRUGS = re.compile(r"(?<!\w)(?:" + "|".join(DRUG_HINTS) + r")(?!\w)", re.I)


def has_banned_title(text: str) -> bool:
    """Whether a title / HUD line / hashtag / publication text carries a drug hint (DRUG_HINTS)."""
    return bool(_DRUGS.search(text or ""))


def clean_text(text: str) -> str:
    """A title / HUD / publication text without the drug hints: the word is cut, the separators around it tidied
    («ACID // TECHNO» -> «TECHNO», «#acid #techno» -> «#techno»). Not for sung words."""
    if not text or not _DRUGS.search(text):
        return text   # nothing to cut: the text is returned as written
    sep = r"[/|\-\u2013\u2014:,]+"
    out = re.sub(r"#?" + _DRUGS.pattern, "", text, flags=re.I)
    out = re.sub(rf"({sep})(?:\s+{sep})+", lambda m: m.group(1), out)   # two separators that met where the word was
    out = re.sub(rf"^\s*{sep}\s*|\s*{sep}\s*$", "", out)
    out = re.sub(r"\s+([,.;!?])", lambda m: m.group(1), out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip()


def apply(plan: dict) -> None:
    """After the writer (or a change of look): style_en starts from the look; the heroes' looks by its rules (a photo's
    hero is the photo - its words stay)."""
    if not active(plan):
        return
    plan["style_en"] = style_for(plan, plan.get("style_en", ""))
    lk = look_of(plan)
    for c in plan.get("cast") or []:
        if not c.get("from_photo") and c.get("en") and c.get("kind") not in ("animal", "robot", "creature"):   # «a real person» is for people
            c["en"] = clean_look(c["en"], lk)


def restyle(plan: dict) -> None:
    """«Пересобрать стиль»: the look changed on a written plan - the old fragment swapped for the new one; the scenes'
    own texts (and a locked scene's) stay as they are."""
    plan["looks_v"] = LOOKS_V
    apply(plan)


def camera_for_singing(plan: dict) -> Optional[str]:
    """The singing scenes' camera by the look: None - the caller's default (the autopilot's push-in / orbit)."""
    return look_of(plan).get("sing_camera") if active(plan) else None


def portrait(plan: dict, who: str, gender: str = "", kind: str = "person") -> tuple[str, str]:
    """(the portrait's opening, an anchor after it) by the look: «A waist-up photo of ...» and «Photo of a real woman,
    natural skin texture.» for a live look. An older plan: the words it always had."""
    if not active(plan):
        return f"A medium close-up photo of {who}", ""
    lk = look_of(plan)
    anchor = ((NONPERSON_PHOTO.get(kind, "") if kind != "person" else WOMAN_PHOTO if gender == "female" else MAN_PHOTO if gender == "male" else "")
              if lk["live"] else "")
    return f"A {lk['portrait']} {lk['medium']} of {who}", anchor


def scene_rules(plan: dict) -> Optional[tuple[float, float]]:
    """The delivery's (min, max) seconds of a scene, when the plan is written by these rules."""
    return tuple(delivery_of(plan)["scene"]) if active(plan) and delivery_of(plan)["scene"] else None


def insert_share(plan: dict, default: float) -> float:
    d = delivery_of(plan)
    return float(d["inserts"]) if active(plan) and d["inserts"] is not None else default


def brief(plan: dict) -> str:
    """The writer's lines about the delivery and the look (they replace «Mood:»)."""
    d, lk = delivery_of(plan), look_of(plan)
    own = own_text(plan)
    cams = ", ".join(d["cameras"])
    out = (f"Delivery: {d['brief']}." + (f" Prefer the cameras {cams}." if cams else "") + "\n"
           f"Look: style_en begins with exactly \"{lk['style_en']}\", then at most 25 words of your own for this video (light, palette, lens).\n")
    if own:
        out += f"The user's own words about the look ({'put them into style_en in English'}): {own}\n"
    mood = str(plan.get("mood") or "").strip()
    if mood and mood not in MOOD_MAP:   # an older client's own «Настроение»: not a delivery, but the user's words
        out += f"Mood: {mood}.\n"
    if lk["live"]:
        out += ("The people are real: their looks name real features (age, face shape, nose, brows, a mole or freckles, skin "
                "with texture); never porcelain, doll-like, flawless, huge or large eyes, long lashes.\n")
    return out


# ---------------------------------------------------------------------------------------------------------------
# «Решит сценарист»: one short call
# ---------------------------------------------------------------------------------------------------------------
PICK_SYSTEM = """You choose how a short video is told (the delivery) and how its picture looks (the look) from two fixed
lists, by the user's song or idea: its genre, mood and words. Answer with the ids from the lists and one short sentence
why, in Russian (why_ru) and in English (why_en). Prefer a live look unless the song or the idea asks for a drawn or
animated world."""


def _pick_user(plan: dict) -> str:
    c = plan.get("clip") or {}
    ds = "\n".join(f"{d['id']}: {d['en']} - {d['hint_en']}" for d in DELIVERIES.values() if d["id"] != AUTO)
    ls = "\n".join(f"{x['id']}: {x['en']} - {x['hint_en']}" for x in offered(plan.get("video") or "h3"))
    what = (f"A music video to the song «{c.get('name', '')}», {float(c.get('bpm') or 0):.0f} BPM.\nThe song's parts and words:\n{(c.get('map') or c.get('words') or '(no words)')[:1500]}\n"
            if c else "")
    return (what + f"The idea: {plan.get('idea') or '(none)'}\n"
            + (f"The user's own words about the look: {own_text(plan)}\n" if own_text(plan) else "")
            + f"\nDeliveries:\n{ds}\n\nLooks:\n{ls}\n")


def needs_pick(plan: dict) -> bool:
    if not active(plan) or plan.get("look_pick"):
        return False
    lk = str(plan.get("look") or AUTO)
    return plan.get("delivery", AUTO) == AUTO or (lk == AUTO)


async def decide(llm, plan: dict) -> Optional[dict]:
    """«Решит сценарист»: a delivery and a look picked by the writer (an open llm client), into plan.look_pick; a
    failed answer - the fallback, said so in `why`. Nothing to do when both are chosen or already picked."""
    if not needs_pick(plan):
        return plan.get("look_pick")
    ids_d = [d for d in DELIVERIES if d != AUTO]
    ids_l = [x["id"] for x in offered(plan.get("video") or "h3")]
    schema = {"type": "object", "properties": {"delivery": {"type": "string", "enum": ids_d}, "look": {"type": "string", "enum": ids_l},
                                               "why_ru": {"type": "string", "maxLength": 200}, "why_en": {"type": "string", "maxLength": 200}},
              "required": ["delivery", "look", "why_ru", "why_en"], "additionalProperties": False}
    fd, fl = fallback(plan)
    try:
        # a small model thinks before it answers (as places.ask): 400 tokens cut gemma-4-E4B off before the JSON - every
        # pick fell back to cinema / live cinema without a word (GPU test 2026-11-03); with 2000 it picked rainy_city
        d = await llm.chat_json(PICK_SYSTEM, _pick_user(plan), schema, temperature=0.4, seed=int(plan.get("seed") or 1), max_tokens=2000, step="look")
        got = {"delivery": d.get("delivery") if d.get("delivery") in ids_d else fd, "look": d.get("look") if d.get("look") in ids_l else fl,
               "why_ru": str(d.get("why_ru") or "").strip()[:200], "why_en": str(d.get("why_en") or "").strip()[:200]}
    except Exception:  # noqa: BLE001 - a pick is never the reason a video is not written
        got = pick_fallback(plan)
    if plan.get("delivery", AUTO) != AUTO:   # only the row left to the writer is its pick
        got["delivery"] = plan["delivery"]
    lk = str(plan.get("look") or AUTO)
    if lk != AUTO:
        got["look"] = resolve(plan)[1]
    plan["look_pick"] = got
    return got


def pick_fallback(plan: dict) -> dict:
    fd, fl = fallback(plan)
    return {"delivery": fd, "look": fl, "why_ru": "сценарист не ответил — взято по умолчанию",
            "why_en": "the writer did not answer: the default is taken", "fallback": True}
