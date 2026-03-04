"""B站视频信息和字幕提取服务"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
from bilibili_api import Credential, video


@dataclass(frozen=True)
class VideoInfo:
    bvid: str
    aid: int
    cid: int
    title: str
    cover: str
    owner_name: str
    owner_face: str
    view_count: int
    danmaku_count: int
    duration: int  # seconds
    desc: str


@dataclass(frozen=True)
class SubtitleItem:
    start: float  # seconds
    end: float
    content: str


@dataclass(frozen=True)
class SubtitleTrack:
    lang: str
    lang_doc: str
    subtitle_url: str
    items: list[SubtitleItem]


def parse_video_id(url: str) -> str:
    """从 B站 URL 中提取 BV号 或 AV号。

    支持格式：
    - https://www.bilibili.com/video/BV1xxxxx
    - https://www.bilibili.com/video/av12345
    - https://b23.tv/xxxxx (短链接会在调用方解析重定向)
    - BV1xxxxx (直接输入 BV号)
    """
    url = url.strip()

    # 直接输入 BV号
    bv_direct = re.match(r"^(BV[A-Za-z0-9]+)$", url)
    if bv_direct:
        return bv_direct.group(1)

    # 标准 URL 中的 BV号
    bv_match = re.search(r"bilibili\.com/video/(BV[A-Za-z0-9]+)", url)
    if bv_match:
        return bv_match.group(1)

    # AV号
    av_match = re.search(r"bilibili\.com/video/av(\d+)", url, re.IGNORECASE)
    if av_match:
        return f"av{av_match.group(1)}"

    # b23.tv 短链接
    if "b23.tv" in url:
        return url  # 返回原始 URL，由调用方解析重定向

    raise ValueError(
        "无法解析视频地址。请输入正确的 B站视频链接，例如：\n"
        "https://www.bilibili.com/video/BV1xxxxxxxxx"
    )


async def resolve_short_url(url: str) -> str:
    """解析 b23.tv 短链接，获取重定向后的实际地址"""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, timeout=10)
        return str(resp.url)


def _build_credential(sessdata: str, bili_jct: str, buvid3: str) -> Credential | None:
    if not sessdata:
        return None
    return Credential(sessdata=sessdata, bili_jct=bili_jct, buvid3=buvid3)


async def get_video_info(
    video_id: str,
    sessdata: str = "",
    bili_jct: str = "",
    buvid3: str = "",
) -> VideoInfo:
    """获取视频基本信息"""
    credential = _build_credential(sessdata, bili_jct, buvid3)

    # 处理短链接
    if video_id.startswith("http") and "b23.tv" in video_id:
        resolved = await resolve_short_url(video_id)
        video_id = parse_video_id(resolved)

    # 构建 Video 对象
    if video_id.startswith("av"):
        v = video.Video(aid=int(video_id[2:]), credential=credential)
    else:
        v = video.Video(bvid=video_id, credential=credential)

    info = await v.get_info()

    return VideoInfo(
        bvid=info["bvid"],
        aid=info["aid"],
        cid=info["pages"][0]["cid"],
        title=info["title"],
        cover=info["pic"],
        owner_name=info["owner"]["name"],
        owner_face=info["owner"]["face"],
        view_count=info["stat"]["view"],
        danmaku_count=info["stat"]["danmaku"],
        duration=info["duration"],
        desc=info.get("desc", ""),
    )


async def get_subtitles(
    bvid: str,
    cid: int,
    sessdata: str = "",
    bili_jct: str = "",
    buvid3: str = "",
) -> list[SubtitleTrack]:
    """获取视频字幕列表及内容"""
    credential = _build_credential(sessdata, bili_jct, buvid3)
    v = video.Video(bvid=bvid, credential=credential)

    # 获取字幕列表
    subtitle_info = await v.get_subtitle(cid)
    subtitles_list = subtitle_info.get("subtitles", [])

    if not subtitles_list:
        return []

    tracks: list[SubtitleTrack] = []

    async with httpx.AsyncClient() as client:
        for sub in subtitles_list:
            sub_url = sub.get("subtitle_url", "")
            if not sub_url:
                continue
            # 确保使用 https
            if sub_url.startswith("//"):
                sub_url = "https:" + sub_url

            try:
                resp = await client.get(sub_url, timeout=10)
                data = resp.json()
                items = [
                    SubtitleItem(
                        start=item["from"],
                        end=item["to"],
                        content=item["content"],
                    )
                    for item in data.get("body", [])
                ]
                tracks.append(
                    SubtitleTrack(
                        lang=sub.get("lan", "unknown"),
                        lang_doc=sub.get("lan_doc", "未知"),
                        subtitle_url=sub_url,
                        items=items,
                    )
                )
            except Exception:
                continue

    return tracks


def format_time_srt(seconds: float) -> str:
    """将秒数转为 SRT 时间格式 HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_subtitle_srt(items: list[SubtitleItem]) -> str:
    """将字幕列表转为 SRT 格式字符串"""
    lines: list[str] = []
    for i, item in enumerate(items, start=1):
        lines.append(str(i))
        lines.append(f"{format_time_srt(item.start)} --> {format_time_srt(item.end)}")
        lines.append(item.content)
        lines.append("")
    return "\n".join(lines)


def format_subtitle_txt(items: list[SubtitleItem]) -> str:
    """将字幕列表转为纯文本（带时间戳）"""
    lines: list[str] = []
    for item in items:
        start_m = int(item.start // 60)
        start_s = int(item.start % 60)
        lines.append(f"[{start_m:02d}:{start_s:02d}] {item.content}")
    return "\n".join(lines)


def format_subtitle_plain(items: list[SubtitleItem]) -> str:
    """将字幕列表转为纯文本（无时间戳）"""
    return "\n".join(item.content for item in items)
