"""
通知模組 (Notification Module)
透過 Telegram Bot API 發送新電影的海報圖片與文字資訊。
"""

import os
import requests
import tempfile
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"


def _get_credentials() -> tuple[str, str]:
    """從環境變數取得 Telegram Bot Token 和 Chat ID。"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token:
        raise ValueError("未設定環境變數 TELEGRAM_BOT_TOKEN")
    if not chat_id:
        raise ValueError("未設定環境變數 TELEGRAM_CHAT_ID")
    return token, chat_id


def _format_message(movie: dict) -> str:
    """組裝電影資訊的 Telegram 訊息（Markdown 格式）。"""
    lines = []
    lines.append(f"🎬 *{_escape_markdown(movie.get('name', '(未知電影)'))}*")

    if movie.get("period"):
        lines.append(f"📅 上映期間：{_escape_markdown(movie['period'])}")
    if movie.get("rating"):
        lines.append(f"🔞 分級：{_escape_markdown(movie['rating'])}")
    if movie.get("duration"):
        lines.append(f"⏱ 片長：{_escape_markdown(movie['duration'])}")
    if movie.get("showtimes"):
        times_str = "　".join(movie["showtimes"])
        lines.append(f"🕐 場次：{_escape_markdown(times_str)}")

    return "\n".join(lines)


def _escape_markdown(text: str) -> str:
    """跳脫 Telegram MarkdownV2 特殊字元。"""
    # 使用一般 Markdown（非 V2），特殊字元較少
    special_chars = ["*", "_", "`", "["]
    for char in special_chars:
        text = text.replace(char, f"\\{char}")
    return text


def _download_poster(poster_url: str) -> Path | None:
    """下載海報圖片至暫存檔案，回傳檔案路徑。"""
    if not poster_url:
        return None
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(poster_url, headers=headers, timeout=30)
        response.raise_for_status()

        # 從 URL 或 Content-Type 判斷副檔名
        content_type = response.headers.get("Content-Type", "")
        if "png" in content_type:
            suffix = ".png"
        elif "gif" in content_type:
            suffix = ".gif"
        elif "webp" in content_type:
            suffix = ".webp"
        else:
            suffix = ".jpg"

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(response.content)
        tmp.close()
        logger.info(f"已下載海報：{poster_url} -> {tmp.name}")
        return Path(tmp.name)
    except requests.RequestException as e:
        logger.warning(f"下載海報失敗 ({poster_url})：{e}")
        return None


def _send_photo(token: str, chat_id: str, photo_path: Path, caption: str) -> bool:
    """透過 Telegram Bot API 發送圖片。"""
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        with open(photo_path, "rb") as photo_file:
            response = requests.post(
                url,
                data={
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": "Markdown",
                },
                files={"photo": photo_file},
                timeout=60,
            )
        result = response.json()
        if result.get("ok"):
            logger.info("成功發送海報圖片")
            return True
        else:
            logger.error(f"發送海報失敗：{result.get('description', '未知錯誤')}")
            return False
    except (requests.RequestException, IOError) as e:
        logger.error(f"發送海報時發生錯誤：{e}")
        return False


def _send_message(token: str, chat_id: str, text: str) -> bool:
    """透過 Telegram Bot API 發送純文字訊息。"""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            },
            timeout=30,
        )
        result = response.json()
        if result.get("ok"):
            logger.info("成功發送文字訊息")
            return True
        else:
            logger.error(f"發送訊息失敗：{result.get('description', '未知錯誤')}")
            return False
    except requests.RequestException as e:
        logger.error(f"發送訊息時發生錯誤：{e}")
        return False


def send_header_message(token: str, chat_id: str, count: int) -> None:
    """發送本次更新的標題訊息。"""
    text = f"🎥 *UCC 影城 - 新電影通知*\n共有 *{count}* 部新電影上映！"
    _send_message(token, chat_id, text)


def notify_new_movies(new_movies: list[dict]) -> None:
    """
    主入口：對所有新電影發送 Telegram 通知。

    Args:
        new_movies: 新電影列表
    """
    if not new_movies:
        logger.info("沒有新電影，不發送通知")
        return

    token, chat_id = _get_credentials()

    # 發送標題訊息
    send_header_message(token, chat_id, len(new_movies))

    for i, movie in enumerate(new_movies, 1):
        name = movie.get("name", "(未知)")
        logger.info(f"正在發送第 {i}/{len(new_movies)} 部電影通知：{name}")

        caption = _format_message(movie)
        poster_url = movie.get("poster_url", "")

        sent = False
        poster_path = None

        # 嘗試下載並發送海報
        if poster_url:
            poster_path = _download_poster(poster_url)
            if poster_path:
                sent = _send_photo(token, chat_id, poster_path, caption)

        # 若無海報或發送失敗，改發純文字
        if not sent:
            if poster_url:
                # 附上海報 URL 作為備用
                caption += f"\n🖼 [海報圖片]({poster_url})"
            _send_message(token, chat_id, caption)

        # 清理暫存圖片
        if poster_path and poster_path.exists():
            try:
                poster_path.unlink()
            except OSError:
                pass

    logger.info(f"已完成 {len(new_movies)} 部電影的通知發送")
