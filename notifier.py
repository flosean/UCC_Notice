"""
通知模組 (Notification Module)
透過 Telegram Bot API 發送新電影的海報圖片與文字資訊。
"""

import os
import html
import time
import requests
import tempfile
import logging
from pathlib import Path

from scraper import USER_AGENT

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
    """組裝電影資訊的 Telegram 訊息（HTML 格式）。

    使用 HTML parse_mode 並以 html.escape 跳脫所有動態欄位，避免片名中的
    特殊字元（如 < & 或落單的 Markdown 符號）導致 Telegram 回傳 400 而送不出。
    """
    esc = html.escape
    lines = [f"🎬 <b>{esc(movie.get('name', '(未知電影)'))}</b>"]

    if movie.get("period"):
        lines.append(f"📅 上映期間：{esc(movie['period'])}")
    if movie.get("rating"):
        lines.append(f"🏷 分級：{esc(movie['rating'])}")
    if movie.get("duration"):
        lines.append(f"⏱ 片長：{esc(movie['duration'])}")
    if movie.get("showtimes"):
        times_str = "　".join(movie["showtimes"])
        lines.append(f"🕐 場次：{esc(times_str)}")

    return "\n".join(lines)


def _download_poster(poster_url: str, max_retries: int = 3) -> Path | None:
    """下載海報圖片至暫存檔案，回傳檔案路徑；對暫時性錯誤自動重試。"""
    if not poster_url:
        return None
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(poster_url, headers=headers, timeout=30)
            response.raise_for_status()

            # 從 Content-Type 判斷副檔名
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
            logger.warning(f"下載海報失敗（第 {attempt}/{max_retries} 次）({poster_url})：{e}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
    return None


def _retry_after_seconds(result: dict) -> int:
    """從 Telegram 429 回應取得建議的等待秒數。"""
    return result.get("parameters", {}).get("retry_after", 1)


def _send_photo(token: str, chat_id: str, photo_path: Path, caption: str) -> bool:
    """透過 Telegram Bot API 發送圖片；遇 429 流量限制時依建議秒數重試一次。"""
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    for _ in range(2):
        try:
            with open(photo_path, "rb") as photo_file:
                response = requests.post(
                    url,
                    data={
                        "chat_id": chat_id,
                        "caption": caption,
                        "parse_mode": "HTML",
                    },
                    files={"photo": photo_file},
                    timeout=60,
                )
            result = response.json()
            if result.get("ok"):
                logger.info("成功發送海報圖片")
                return True
            if response.status_code == 429:
                wait = _retry_after_seconds(result)
                logger.warning(f"觸發 Telegram 流量限制，{wait} 秒後重試")
                time.sleep(wait + 1)
                continue
            logger.error(f"發送海報失敗：{result.get('description', '未知錯誤')}")
            return False
        except (requests.RequestException, IOError) as e:
            logger.error(f"發送海報時發生錯誤：{e}")
            return False
    return False


def _send_message(token: str, chat_id: str, text: str) -> bool:
    """透過 Telegram Bot API 發送文字訊息；遇 429 流量限制時依建議秒數重試一次。"""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for _ in range(2):
        try:
            response = requests.post(
                url,
                data={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
                timeout=30,
            )
            result = response.json()
            if result.get("ok"):
                logger.info("成功發送文字訊息")
                return True
            if response.status_code == 429:
                wait = _retry_after_seconds(result)
                logger.warning(f"觸發 Telegram 流量限制，{wait} 秒後重試")
                time.sleep(wait + 1)
                continue
            logger.error(f"發送訊息失敗：{result.get('description', '未知錯誤')}")
            return False
        except requests.RequestException as e:
            logger.error(f"發送訊息時發生錯誤：{e}")
            return False
    return False


def send_header_message(token: str, chat_id: str, count: int) -> None:
    """發送本次更新的標題訊息。"""
    text = f"🎥 <b>UCC 影城 - 新電影通知</b>\n共有 <b>{count}</b> 部新電影上映！"
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
                caption += f'\n🖼 <a href="{html.escape(poster_url, quote=True)}">海報圖片</a>'
            _send_message(token, chat_id, caption)

        # 清理暫存圖片
        if poster_path and poster_path.exists():
            try:
                poster_path.unlink()
            except OSError:
                pass

        # 訊息之間稍作間隔，避免觸發 Telegram 流量限制
        if i < len(new_movies):
            time.sleep(1)

    logger.info(f"已完成 {len(new_movies)} 部電影的通知發送")
