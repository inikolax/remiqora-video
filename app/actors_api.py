"""The actors' HTTP side: the library (data/actors/, or a series' own: `?series=<sid>`), a sheet's and the tries' jobs in the
studio's queue (the same pattern as the heroes' tries in main.py), «В библиотеку» from a graph hero or a project's cast
member. actors.py does the work."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field

from . import actors, config, graph, i18n, jobs, picture, projects

router = APIRouter()
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
MAX_UPLOAD = 30 * 1024 * 1024   # a photo upload's size cap


def _base(series: Optional[str]) -> Optional[Path]:
    if not series:
        return None
    try:
        return actors.series_root(series)
    except ValueError as e:
        raise HTTPException(400, i18n.L("Плохой номер сериала", "Bad series id")) from e


def _get(aid: str, base: Optional[Path]) -> dict:
    try:
        return actors.get(aid, base)
    except KeyError as e:
        raise HTTPException(404, i18n.L("Нет такого актёра", "No such actor")) from e


def _check_drawing() -> None:
    if why := picture.edit_problem():
        raise HTTPException(400, why)


class ActorBody(BaseModel):
    name: str = Field("", max_length=200)
    look_en: str = Field("", max_length=2000)
    look_ru: str = Field("", max_length=2000)
    outfit_en: str = Field("", max_length=1000)
    outfit_ru: str = Field("", max_length=1000)
    voice_en: str = Field("", max_length=500)
    kind: str = "person"
    look: str = ""


@router.get("/api/actors")
def actors_list(series: Optional[str] = None):
    return {"actors": actors.list_all(_base(series)), "kinds": list(actors.KINDS)}


@router.post("/api/actors")
def actor_create(body: ActorBody, series: Optional[str] = None):
    if not body.name.strip():
        raise HTTPException(400, i18n.L("Назовите актёра", "Name the actor"))
    return actors.public(actors.save(body.model_dump(), _base(series)), _base(series))


@router.put("/api/actors/{aid}")
def actor_update(aid: str, body: ActorBody, series: Optional[str] = None):
    base = _base(series)
    _get(aid, base)
    return actors.public(actors.save({**body.model_dump(), "id": aid}, base), base)


@router.delete("/api/actors/{aid}")
def actor_delete(aid: str, series: Optional[str] = None):
    base = _base(series)
    _get(aid, base)
    _refuse_while_drawing(aid, series)   # a drawing job would write into a folder that is gone
    actors.delete(aid, base)
    return {"ok": True}


@router.get("/api/actors/{aid}/image/{which}")
def actor_image(aid: str, which: str, series: Optional[str] = None):
    base = _base(series)
    try:
        p = actors.image_path(aid, which, base)
    except KeyError as e:
        raise HTTPException(404, i18n.L("Нет такой картинки", "No such picture")) from e
    if not p.exists():
        raise HTTPException(404, i18n.L("Картинки нет", "No picture"))
    return FileResponse(p, headers={"Cache-Control": "no-cache"})


@router.get("/api/actors/{aid}/tries/{name}")
def actor_try_image(aid: str, name: str, series: Optional[str] = None):
    try:
        p = actors.try_path(aid, name, _base(series))
    except KeyError as e:
        raise HTTPException(404, i18n.L("Нет такой пробы", "No such try")) from e
    if not p.exists():
        raise HTTPException(404, i18n.L("Пробы нет", "No try"))
    return FileResponse(p, headers={"Cache-Control": "no-cache"})


def _refuse_while_drawing(aid: str, series: Optional[str]) -> None:
    """409 while a sheet or tries job of THIS actor (of this library) is queued or running: it would write face.png and turn.png
    from the old reference after the new photo or crop had removed them."""
    for j in list(jobs.JOBS.values()):
        if (j.kind in ("actor_sheet", "actor_tries") and j.status in ("queued", "running")
                and j.params.get("actor") == aid and (j.params.get("series") or None) == (series or None)):
            raise HTTPException(409, i18n.L("Сейчас рисуется лист этого героя — дождитесь или остановите задачу",
                                            "This hero's sheet is being drawn right now - wait for it or stop the job"))


@router.post("/api/actors/{aid}/photo")
async def actor_photo(aid: str, file: UploadFile, series: Optional[str] = None):
    """The actor's photo (a real one, or any picture of the person). One person in it: crop the others out (/crop)."""
    base = _base(series)
    _get(aid, base)
    _refuse_while_drawing(aid, series)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in IMAGE_EXT:
        raise HTTPException(400, i18n.L("Нужна картинка: png, jpg или webp", "A picture is needed: png, jpg or webp"))
    tmp = config.DATA_DIR / f"actor_up_{uuid.uuid4().hex[:8]}{ext}"
    try:
        size = 0
        with open(tmp, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(400, i18n.L("Файл больше 30 МБ", "The file is larger than 30 MB"))
                f.write(chunk)
        _refuse_while_drawing(aid, series)   # a job may have started while the file was uploading
        try:
            actors.put_image(aid, "photo", tmp, base)
        except (OSError, ValueError, Image.DecompressionBombError) as e:   # DecompressionBombError is NOT a ValueError (it derives from Exception), so it is named
            raise HTTPException(400, i18n.L("Картинка не читается или слишком велика", "The picture can't be read or is too large")) from e
        (actors.folder(aid, base) / "original.png").unlink(missing_ok=True)
        a = _get(aid, base)
        a.pop("photo_drawn", None)
        actors._write(a, base)
    finally:
        tmp.unlink(missing_ok=True)
    return actors.public(_get(aid, base), base)


class CropBody(BaseModel):
    box: list[float] = Field(..., min_length=4, max_length=4)   # x, y, w, h: pixels, or shares of the picture when all are <= 1


@router.post("/api/actors/{aid}/crop")
def actor_crop(aid: str, body: CropBody, series: Optional[str] = None):
    """«Вырезать героя»: the box of the actor's photo becomes the photo (the whole picture is kept as original.png the first time)."""
    base = _base(series)
    _get(aid, base)
    _refuse_while_drawing(aid, series)
    photo = actors.image_path(aid, "photo", base)
    d = actors.folder(aid, base)
    if not photo.exists():
        raise HTTPException(400, i18n.L("У актёра нет фото", "The actor has no photo"))
    src = d / "original.png"
    if not src.exists():
        shutil.copyfile(photo, src)
    try:
        actors.crop(src, tuple(body.box), photo)
    except (ValueError, OSError, OverflowError, Image.DecompressionBombError) as e:
        raise HTTPException(400, str(e) or i18n.L("Картинка не читается", "The picture can't be read")) from e
    for old in ("ref", "face", "turn"):   # another crop is another face: the sheet is drawn again
        (d / f"{old}.png").unlink(missing_ok=True)
    return actors.public(_get(aid, base), base)


@router.post("/api/actors/{aid}/sheet")
def actor_sheet(aid: str, series: Optional[str] = None):
    """«Нарисовать лист»: face + turnaround by FLUX.2 Klein (Krea 2 draws the figure first when there is no photo)."""
    base = _base(series)
    a = _get(aid, base)
    if not actors.reference(a, base):
        if not (a.get("look_en") or "").strip():
            raise HTTPException(400, i18n.L("Нужно фото или описание внешности по-английски", "A photo or a look in English is needed"))
        if why := picture.problem():
            raise HTTPException(400, why)
    _check_drawing()
    return jobs.submit_task("actor_sheet", {"actor": aid, "series": series}, lambda job: actors.draw_sheet(job, aid, base), estimate=40).public()


class TriesBody(BaseModel):
    looks: list[str] = []
    seeds: int = 2


@router.post("/api/actors/{aid}/tries")
def actor_tries(aid: str, body: TriesBody, series: Optional[str] = None):
    """«Пробы»: the face in up to four looks x `seeds` seeds."""
    base = _base(series)
    _get(aid, base)
    keys = actors.pick_looks(body.looks)
    if not keys:
        raise HTTPException(400, i18n.L("Выберите хотя бы один вид", "Pick at least one look"))
    _check_drawing()
    seeds = max(1, min(int(body.seeds), 4))
    return jobs.submit_task("actor_tries", {"actor": aid, "series": series, "looks": keys, "seeds": seeds},
                            lambda job: actors.tries(job, aid, keys, seeds, base), estimate=12 * len(keys) * seeds + 10).public()


class PickBody(BaseModel):
    sheet: bool = True   # redraw the sheet in the chosen look at once


@router.post("/api/actors/{aid}/tries/{name}/pick")
def actor_try_pick(aid: str, name: str, body: PickBody = PickBody(), series: Optional[str] = None):
    """A try becomes the actor's look; the sheet is redrawn in it (a job; `job` in the answer) unless `sheet` is false."""
    base = _base(series)
    _get(aid, base)
    _refuse_while_drawing(aid, series)
    if body.sheet:
        _check_drawing()
    try:
        a = actors.pick_try(aid, name, base)
    except KeyError as e:
        raise HTTPException(404, i18n.L("Нет такой пробы", "No such try")) from e
    job = jobs.submit_task("actor_sheet", {"actor": aid, "series": series}, lambda job: actors.draw_sheet(job, aid, base), estimate=40).public() if body.sheet else None
    return {"actor": a, "job": job}


@router.delete("/api/actors/{aid}/tries")
def actor_tries_clear(aid: str, series: Optional[str] = None):
    base = _base(series)
    _get(aid, base)
    _refuse_while_drawing(aid, series)
    actors.clear_tries(aid, base)
    return actors.public(_get(aid, base), base)


class FromHero(BaseModel):
    project: str
    node: Optional[str] = None   # a graph project's «Герой» node
    cast: Optional[int] = None   # a storyboard project's cast member
    name: str = Field("", max_length=200)


@router.post("/api/actors/from-hero")
def actor_from_hero(body: FromHero, series: Optional[str] = None):
    """«В библиотеку»: a hero of a project becomes an actor (the look, the outfit, the kind, the photo)."""
    base = _base(series)
    try:
        proj = projects.load(body.project)
    except projects.NotFound as e:
        raise HTTPException(404, i18n.L("Проект не найден", "Project not found")) from e
    if body.node is not None:
        n = graph.node(graph.load(body.project), body.node)
        if not n or n["type"] != "hero":
            raise HTTPException(404, i18n.L("Нет такого героя", "No such hero"))
        d = actors.hero_data(n["data"], actors.library_for(proj, n["data"].get("actor") or ""))   # the project's library, as the graph looks it up; a node already linked to an actor: the actor's look, not the template's leftovers
    else:
        cast = (proj.get("plan") or {}).get("cast") or []
        if body.cast is None or not 0 <= body.cast < len(cast):
            raise HTTPException(404, i18n.L("Нет такого героя", "No such hero"))
        d = cast[body.cast]
    if not any((d.get(k) or "").strip() for k in ("en", "ru")) and not d.get("photo"):
        raise HTTPException(400, i18n.L("У героя нет ни описания, ни фото", "The hero has neither a look nor a photo"))
    return actors.from_hero(d, projects.folder(body.project), body.name.strip() or d.get("title") or "", base)
