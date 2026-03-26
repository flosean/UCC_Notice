"""
資料比較與新電影偵測模組 (Data Comparison & New Movie Detection Module)
比較當前電影列表與歷史資料，識別新電影。
"""

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).parent / "movies_data.json"


def _make_movie_id(movie: dict) -> str:
    """建立電影的唯一識別碼（電影名稱 + 上映期間）。"""
    name = movie.get("name", "").strip()
    period = movie.get("period", "").strip()
    return f"{name}|{period}" if period else name


def load_history() -> dict[str, dict]:
    """從 JSON 文件讀取歷史電影資料，回傳以 movie_id 為 key 的字典。"""
    if not DATA_FILE.exists():
        logger.info("歷史資料文件不存在，視為首次執行")
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 支援舊格式（list）與新格式（dict）
        if isinstance(data, list):
            return {_make_movie_id(m): m for m in data}
        return data
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"讀取歷史資料失敗：{e}")
        return {}


def save_history(movies: list[dict]) -> bool:
    """將最新電影列表存回 JSON 文件。"""
    movie_dict = {_make_movie_id(m): m for m in movies}
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(movie_dict, f, ensure_ascii=False, indent=2)
        logger.info(f"已儲存 {len(movies)} 部電影資料至 {DATA_FILE}")
        return True
    except IOError as e:
        logger.error(f"儲存電影資料失敗：{e}")
        return False


def detect_new_movies(current_movies: list[dict]) -> list[dict]:
    """
    比較當前電影列表與歷史資料，返回所有新電影。

    Args:
        current_movies: 本次爬取的電影列表

    Returns:
        新電影列表（在歷史資料中找不到的電影）
    """
    history = load_history()
    is_first_run = len(history) == 0

    new_movies = []
    for movie in current_movies:
        movie_id = _make_movie_id(movie)
        if not movie_id.strip():
            continue
        if movie_id not in history:
            new_movies.append(movie)
            logger.info(f"偵測到新電影：{movie.get('name', '(未知)')}")

    if is_first_run and current_movies:
        logger.info("首次執行，將所有電影視為新電影並發送通知")
        new_movies = current_movies

    logger.info(f"共偵測到 {len(new_movies)} 部新電影")
    return new_movies
