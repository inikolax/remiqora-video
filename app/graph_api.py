"""The graph's HTTP side (phase 9): a graph project's canvas, its state, its runs, its LLM nodes, files, templates,
cleaning, and the ways between a storyboard and a graph. graph.py and graph_io.py do the work."""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import config, edit, graph, graph_io, i18n, jobs, picture, projects, videomodels
from .engine import graphs
from .engine.comfy import COMFY
from .llm import client as llm

router = APIRouter()
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".webm"}


def _project(pid: str, kind: Optional[str] = "graph") -> dict:
    try:
        proj = projects.load(pid)
    except projects.NotFound as e:
        raise HTTPException(404, i18n.L("Проект не найден", "Project not found")) from e
    if kind == "graph" and proj.get("type") != "graph":
        raise HTTPException(400, i18n.L("Это раскадровка, а не граф", "This is a storyboard, not a graph"))
    return proj


def _busy(pid: str) -> bool:
    return any(j.status in ("queued", "running") and j.params.get("project") == pid for j in jobs.JOBS.values())


@router.get("/api/graph/types")
def graph_types():
    return {"types": graph.public_types(), "picture": picture.status(), "length": graph.LENGTH_S}


class NewGraph(BaseModel):
    name: str = Field("", max_length=120)
    aspect: str = "16:9"
    template: Optional[str] = None
    video_model: str = "h3"          # phase 10: which model shoots its scenes


@router.post("/api/graphs")
def new_graph(req: NewGraph):
    if req.aspect not in graphs.ASPECTS:
        raise HTTPException(400, i18n.L(f"Неизвестный формат кадра: {req.aspect}", f"Unknown frame format: {req.aspect}"))
    g = None
    if req.template:
        t = next((x for x in graph_io.templates() if x["id"] == req.template), None)
        if not t:
            raise HTTPException(404, i18n.L("Нет такого шаблона", "No such template"))
        g = _fresh_ids({"nodes": t["nodes"], "edges": t["edges"]})
    proj = graph_io.new_project(req.name or i18n.L("Граф", "Graph"), req.aspect, g=g)
    if videomodels.offered(req.video_model) and req.video_model != "h3":
        proj["settings"]["video_model"] = req.video_model
        projects.save(proj)
    return {"project": proj["id"]}


def _fresh_ids(g: dict) -> dict:
    ids = {n["id"]: uuid.uuid4().hex[:8] for n in g["nodes"]}
    nodes = [{**n, "id": ids[n["id"]], "data": _remap(dict(n.get("data") or {}), ids)} for n in g["nodes"]]
    edges = [{**e, "id": uuid.uuid4().hex[:8], "source": ids.get(e["source"]), "target": ids.get(e["target"])}
             for e in g["edges"] if e["source"] in ids and e["target"] in ids]
    return {"rev": 0, "nodes": nodes, "edges": edges}


def _remap(d: dict, ids: dict) -> dict:
    if isinstance(d.get("order"), list):
        d["order"] = [ids.get(x, x) for x in d["order"]]
    return d


@router.get("/api/projects/{pid}/nodes")
def get_nodes(pid: str):
    _project(pid)
    return graph.load(pid)


class GraphDoc(BaseModel):
    rev: Optional[int] = None
    nodes: list[dict] = []
    edges: list[dict] = []


@router.put("/api/projects/{pid}/nodes")
def put_nodes(pid: str, body: GraphDoc):
    _project(pid)
    try:
        return graph.save(pid, body.model_dump(), body.rev)
    except graph.Conflict:
        raise HTTPException(409, {"message": i18n.L("Граф изменился на сервере", "The graph changed on the server"), "graph": graph.load(pid)})


@router.get("/api/projects/{pid}/nodes/state")
def nodes_state(pid: str, quality: Optional[str] = None):
    proj = _project(pid)
    if quality and quality not in graphs.QUALITY_MP:
        raise HTTPException(400, i18n.L(f"Неизвестное качество: {quality}", f"Unknown quality: {quality}"))
    return graph.state(proj, graph.load(pid), quality)


class RunRequest(BaseModel):
    targets: list[str] = []          # empty: every output
    quality: Optional[str] = None


@router.post("/api/projects/{pid}/nodes/run")
def nodes_run(pid: str, req: RunRequest):
    """«Снять всё» / «Снять до сюда»: one queue job; the LLM nodes are not part of it."""
    proj = _project(pid)
    if issues := COMFY.problems():
        raise HTTPException(400, "; ".join(issues))
    if any(j.status in ("queued", "running") and j.kind == "graph" and j.params.get("project") == pid for j in jobs.JOBS.values()):
        raise HTTPException(409, i18n.L("Этот граф уже снимается", "This graph is already being shot"))
    q = req.quality or proj["settings"].get("quality", "draft")
    if q not in graphs.QUALITY_MP:
        raise HTTPException(400, i18n.L(f"Неизвестное качество: {q}", f"Unknown quality: {q}"))
    if q != proj["settings"].get("quality"):
        proj["settings"]["quality"] = q
        projects.save(proj)
    st = graph.state(proj, graph.load(pid), q)
    return jobs.submit_task("graph", {"project": pid, "quality": q, "targets": req.targets, "scenes": st["to_shoot"],
                                      "model": videomodels.of(proj["settings"]).short},
                            lambda job: graph.run(job, pid, req.targets or None, q), estimate=st["seconds"] + 10).public()


class LlmRequest(BaseModel):
    ids: list[str]
    model: Optional[str] = None


@router.post("/api/projects/{pid}/nodes/llm")
def nodes_llm(pid: str, req: LlmRequest):
    """«Написать» / «Описать по фото» / «Придумать реплики» / «Переписать устаревшие»: the LLM nodes, one model load
    for all."""
    _project(pid)
    g = graph.load(pid)
    todo = [graph.node(g, i) for i in req.ids if graph.node(g, i) and graph.node(g, i)["type"] in graph.LLM_BUTTONS]
    if not todo:
        raise HTTPException(400, i18n.L("Нет узлов сценариста, героя или промта", "No writer, hero or prompt nodes"))
    try:
        m = llm.find(req.model)
    except llm.LLMError as e:
        raise HTTPException(400, str(e)) from e
    if any(n["type"] == "hero" for n in todo) and not m.mmproj:
        raise HTTPException(400, i18n.L(f"Модель {m.name} не видит картинок: выберите другую в шапке",
                                          f"Model {m.name} can't see pictures: choose another one in the header"))
    n_writers = sum(1 for n in todo if n["type"] == "writer")
    return jobs.submit_task("graph-llm", {"project": pid, "ids": [n["id"] for n in todo], "model": m.id},
                            lambda job: graph.run_llm(job, pid, [n["id"] for n in todo], m.id),
                            estimate=15 + 25 * (len(todo) - n_writers) + 40 * n_writers).public()


class ExpandRequest(BaseModel):
    node: str


@router.post("/api/projects/{pid}/nodes/expand")
def nodes_expand(pid: str, req: ExpandRequest):
    _project(pid)
    try:
        return graph.expand(pid, req.node)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/projects/{pid}/nodes/upload")
async def nodes_upload(pid: str, file: UploadFile, kind: str = "image"):
    """A photo (Фото, Герой) or a track (Трек) into the project; the node keeps its name."""
    _project(pid)
    ext = Path(file.filename or "").suffix.lower()
    allowed = IMAGE_EXT if kind == "image" else AUDIO_EXT
    if ext not in allowed:
        raise HTTPException(400, i18n.L("Нужна картинка: png, jpg или webp", "A picture is needed: png, jpg or webp") if kind == "image"
                            else i18n.L("Нужен звук: mp3, wav, m4a, flac или ogg", "A sound is needed: mp3, wav, m4a, flac or ogg"))
    name = f"{'img' if kind == 'image' else 'audio'}_{uuid.uuid4().hex[:8]}{ext}"
    dest = projects.folder(pid) / name
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    if ext == ".webm":   # a voice recorded in the browser (Opus): kept as WAV, which every reader takes
        wav = dest.with_suffix(".wav")
        r = await asyncio.to_thread(subprocess.run, [config.FFMPEG, "-y", "-v", "error", "-i", str(dest), "-ac", "1", "-ar", "48000", str(wav)],
                                    capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        dest.unlink(missing_ok=True)
        if r.returncode:
            raise HTTPException(400, i18n.L("Запись не читается: ", "The recording can't be read: ") + (r.stderr or "").strip()[-300:])
        name = wav.name
    return {"file": name, "name": Path(file.filename or name).name}


@router.get("/api/projects/{pid}/nodes/cleanup")
def cleanup_preview(pid: str):
    return graph_io.cleanup(_project(pid))


@router.post("/api/projects/{pid}/nodes/cleanup")
def cleanup_do(pid: str):
    proj = _project(pid)
    if _busy(pid):
        raise HTTPException(409, i18n.L("Граф сейчас снимается", "The graph is being shot now"))
    return graph_io.cleanup(proj, do=True)


@router.post("/api/projects/{pid}/to-graph")
def to_graph(pid: str):
    """«Копия — проект-граф»: a new graph project from this storyboard (the storyboard stays as it is)."""
    src = _project(pid, kind=None)
    if src.get("type") == "graph":
        raise HTTPException(400, i18n.L("Это уже граф", "This is already a graph"))
    try:
        return {"project": graph_io.from_storyboard(src)["id"]}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/projects/{pid}/to-storyboard")
def to_storyboard(pid: str):
    """«Собрать раскадровку»: a new storyboard from a linear graph."""
    proj = _project(pid)
    try:
        return {"project": graph_io.to_storyboard(proj)["id"]}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# ---------- a «Монтаж» node's montage: the same editor as a storyboard's, its montage kept in the node ----------
def _montage_view(proj: dict, nid: str) -> dict:
    g = graph.load(proj["id"])
    n = graph.node(g, nid)
    if not n or n["type"] != "montage":
        raise HTTPException(404, i18n.L("Нет такого узла «Монтаж»", "No such «Montage» node"))
    c = graph.Ctx(proj, g)
    ed = graph.montage_of(c, nid)
    a = graph.evaluate_node(c, nid)
    sig = edit.signature(ed)
    to_shoot = sum(1 for s, _ in c.inputs(nid, "clips") if graph.evaluate_node(c, s).state != "ready")
    return {**ed, "quality": c.quality, "width": c.w, "height": c.h, "fps": edit.FPS, "sig": sig,
            "built_sig": sig if a.state == "ready" else None, "built": a.state == "ready", "to_shoot": to_shoot,
            "track": None, "kind": "graph", "node": nid, "title": n["data"].get("title") or i18n.L("Монтаж", "Montage"), "rev": g.get("rev", 0),
            "state": a.state, "error": a.error}


@router.get("/api/projects/{pid}/nodes/{nid}/edit")
def node_edit(pid: str, nid: str):
    return _montage_view(_project(pid), nid)


class MontageBody(BaseModel):
    clips: list[dict]
    off: list[str] = []
    sounds: list[dict] = []
    overlays: list[dict] = []
    duck: float = 0
    grade: Optional[str] = None
    lut: Optional[str] = None
    match: bool = False
    color: Optional[dict] = None
    scene_colors: dict[str, dict] = {}
    lut_mix: float = 1               # how much of the LUT (edit.look_of)
    vignette: float = 0
    grain: float = 0


@router.put("/api/projects/{pid}/nodes/{nid}/edit")
def node_edit_put(pid: str, nid: str, body: MontageBody):
    proj = _project(pid)
    _montage_view(proj, nid)   # the node is there and is a «Монтаж»

    def put(g: dict) -> None:
        n = graph.node(g, nid)
        if n:
            n["data"]["edit"] = edit.stored(body.model_dump())
    graph.update(pid, put)
    return _montage_view(proj, nid)


@router.delete("/api/projects/{pid}/nodes/{nid}/edit")
def node_edit_reset(pid: str, nid: str):
    """«Как на входе»: the clips as they come in, whole, joined like «Склейка» joins them."""
    proj = _project(pid)
    _montage_view(proj, nid)
    graph.update(pid, lambda g: (graph.node(g, nid) or {"data": {}})["data"].pop("edit", None))
    return _montage_view(proj, nid)


@router.get("/api/graph/templates")
def list_templates():
    return graph_io.templates()


class TemplateBody(BaseModel):
    name: str = Field(..., max_length=200)
    about: str = Field("", max_length=1000)
    nodes: list[dict]
    edges: list[dict] = []
    replace: bool = True          # False: a loaded JSON - a name already taken gets « (2)»


@router.post("/api/graph/templates")
def save_template(body: TemplateBody):
    """«Сохранить выделенное как шаблон» and «Загрузить из JSON»: the nodes are checked like a saved graph (known
    types, links only between ports of one type); what does not fit is dropped and counted in the answer."""
    if not body.nodes:
        raise HTTPException(400, i18n.L("Шаблон пустой: выделите узлы", "The template is empty: select nodes"))
    try:
        return graph_io.save_template(body.name, body.about, body.nodes, body.edges, body.replace)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/api/graph/templates/{tid}")
def delete_template(tid: str):
    try:
        graph_io.delete_template(tid)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}
