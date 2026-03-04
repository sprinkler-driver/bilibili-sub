"""B站视频字幕提取器 — FastAPI 应用"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv, set_key
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import bilibili_service as bs

# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)

app = FastAPI(title="B站字幕提取器")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# 内存缓存最近查询的字幕，供导出使用
_subtitle_cache: dict[str, list[bs.SubtitleTrack]] = {}


def _get_credential() -> dict[str, str]:
    """从环境变量读取 Cookie"""
    return {
        "sessdata": os.getenv("SESSDATA", ""),
        "bili_jct": os.getenv("BILI_JCT", ""),
        "buvid3": os.getenv("BUVID3", ""),
    }


def _format_duration(seconds: int) -> str:
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _format_view_count(count: int) -> str:
    if count >= 100_000_000:
        return f"{count / 100_000_000:.1f}亿"
    if count >= 10_000:
        return f"{count / 10_000:.1f}万"
    return str(count)


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    cred = _get_credential()
    has_cookie = bool(cred["sessdata"])
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "has_cookie": has_cookie},
    )


@app.post("/api/parse", response_class=HTMLResponse)
async def parse_video(request: Request, url: str = Form(...)):
    """解析视频 URL，返回视频信息 + 字幕的 HTMX partial"""
    cred = _get_credential()

    try:
        video_id = bs.parse_video_id(url)
        info = await bs.get_video_info(video_id, **cred)
        subtitles = await bs.get_subtitles(info.bvid, info.cid, **cred)

        # 缓存字幕供导出使用
        _subtitle_cache[info.bvid] = subtitles

        return templates.TemplateResponse(
            "partials/video_result.html",
            {
                "request": request,
                "info": info,
                "subtitles": subtitles,
                "duration_str": _format_duration(info.duration),
                "view_str": _format_view_count(info.view_count),
                "danmaku_str": _format_view_count(info.danmaku_count),
            },
        )
    except ValueError as e:
        return HTMLResponse(
            f'<div class="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 mt-4">'
            f'<p class="font-medium">输入错误</p>'
            f"<p>{e}</p></div>"
        )
    except Exception as e:
        error_msg = str(e)
        if "credential" in error_msg.lower() or "-101" in error_msg:
            hint = "请先在设置中配置 B站 Cookie。"
        else:
            hint = f"请检查视频链接是否正确。错误详情：{error_msg}"
        return HTMLResponse(
            f'<div class="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 mt-4">'
            f'<p class="font-medium">解析失败</p>'
            f"<p>{hint}</p></div>"
        )


@app.get("/api/export/{bvid}")
async def export_subtitle(bvid: str, fmt: str = "srt", lang: str = ""):
    """导出字幕文件"""
    # 如果缓存中没有，重新获取
    if bvid not in _subtitle_cache:
        cred = _get_credential()
        try:
            info = await bs.get_video_info(bvid, **cred)
            tracks = await bs.get_subtitles(info.bvid, info.cid, **cred)
            _subtitle_cache[bvid] = tracks
        except Exception:
            return PlainTextResponse("无法获取字幕", status_code=404)

    tracks = _subtitle_cache.get(bvid, [])
    if not tracks:
        return PlainTextResponse("该视频没有字幕", status_code=404)

    # 选择语言轨道
    track = tracks[0]
    if lang:
        for t in tracks:
            if t.lang == lang:
                track = t
                break

    if fmt == "txt":
        content = bs.format_subtitle_txt(track.items)
        filename = f"{bvid}_{track.lang}.txt"
    else:
        content = bs.format_subtitle_srt(track.items)
        filename = f"{bvid}_{track.lang}.srt"

    return PlainTextResponse(
        content,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/plain; charset=utf-8",
        },
    )


@app.get("/api/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    """返回设置表单 partial"""
    cred = _get_credential()
    return templates.TemplateResponse(
        "partials/settings.html",
        {"request": request, **cred},
    )


@app.post("/api/settings", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    sessdata: str = Form(""),
    bili_jct: str = Form(""),
    buvid3: str = Form(""),
):
    """保存 Cookie 到 .env 文件"""
    if not ENV_PATH.exists():
        ENV_PATH.touch()

    set_key(str(ENV_PATH), "SESSDATA", sessdata)
    set_key(str(ENV_PATH), "BILI_JCT", bili_jct)
    set_key(str(ENV_PATH), "BUVID3", buvid3)

    # 更新当前进程的环境变量
    os.environ["SESSDATA"] = sessdata
    os.environ["BILI_JCT"] = bili_jct
    os.environ["BUVID3"] = buvid3

    return HTMLResponse(
        '<div class="bg-green-50 border border-green-200 text-green-700 rounded-lg p-4">'
        '<p class="font-medium">保存成功！</p>'
        "<p>Cookie 已保存，现在可以解析视频了。</p>"
        "</div>"
    )


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
