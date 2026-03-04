# B站视频字幕提取器

输入 B站视频 URL，预览视频并提取字幕内容。支持导出 SRT / TXT 格式，一键复制全文。

## 功能

- 输入 B站视频链接，显示视频信息（标题、UP主、播放量等）
- 嵌入 B站播放器预览视频
- 提取字幕内容（带时间戳）
- 导出字幕为 SRT 或 TXT 文件
- 一键复制字幕全文
- 页面内配置 B站 Cookie

## 快速开始

```bash
git clone https://github.com/sprinkler-driver/bilibili-sub.git
cd bilibili-sub
pip install -r requirements.txt
python3 app.py
```

浏览器打开 http://localhost:8000

## 配置 Cookie

获取字幕需要 B站登录态。首次使用请点击页面右上角「Cookie 设置」：

1. 打开 [bilibili.com](https://www.bilibili.com) 并登录
2. 按 F12 打开开发者工具
3. 进入 Application → Cookies → bilibili.com
4. 复制 `SESSDATA`、`bili_jct`、`buvid3` 三个值填入设置页面

## 支持的 URL 格式

- `https://www.bilibili.com/video/BV1xxxxxxxxx`
- `https://www.bilibili.com/video/av12345`
- `https://b23.tv/xxxxx`（短链接）
- 直接输入 BV 号

## 技术栈

- **后端**：FastAPI + bilibili-api-python
- **前端**：HTMX + Tailwind CSS（CDN，零构建）
