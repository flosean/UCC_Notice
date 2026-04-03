"""
網頁爬蟲模組 (Web Scraper Module)
訪問 UCC 影城網站，提取電影資訊與海報圖片 URL。
"""

import requests
from bs4 import BeautifulSoup
import re
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TARGET_URL = "http://www.ucc-cinema.com.tw/main03.asp"
BASE_URL = "http://www.ucc-cinema.com.tw"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}


def fetch_page(url: str) -> BeautifulSoup | None:
    """發送 HTTP GET 請求並解析 HTML。"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        # 嘗試使用 big5 解碼（台灣舊網站常用編碼）
        response.encoding = response.apparent_encoding or "big5"
        soup = BeautifulSoup(response.text, "html.parser")
        logger.info(f"成功取得頁面：{url}")
        return soup
    except requests.RequestException as e:
        logger.error(f"無法取得頁面 {url}：{e}")
        return None


def resolve_url(src: str) -> str:
    """將相對 URL 轉換為絕對 URL。"""
    if not src:
        return ""
    src = src.strip()
    if src.startswith("http://") or src.startswith("https://"):
        return src
    if src.startswith("//"):
        return "http:" + src
    if src.startswith("/"):
        return BASE_URL + src
    return BASE_URL + "/" + src


def extract_movies(soup: BeautifulSoup) -> list[dict]:
    """
    從解析後的 HTML 中提取所有電影資訊。
    UCC 影城網站使用 table 佈局，每部電影佔一個區塊。
    """
    movies = []

    # 策略：尋找含有電影海報的 <img> 標籤附近的電影資訊區塊
    # UCC 網站結構：每部電影通常包含海報圖、電影名稱、上映資訊
    movie_blocks = _find_movie_blocks(soup)

    if not movie_blocks:
        logger.warning("未找到電影區塊，嘗試備用解析策略")
        movie_blocks = _fallback_find_movie_blocks(soup)

    for block in movie_blocks:
        movie = _parse_movie_block(block)
        if not movie or not movie.get("name"):
            continue
        expanded = _expand_paired_movie(movie)
        movies.extend(expanded)
        for m in expanded:
            logger.info(f"  解析電影：{m['name']}")

    logger.info(f"共解析到 {len(movies)} 部電影")
    return movies


def _find_movie_blocks(soup: BeautifulSoup) -> list:
    """主要解析策略：尋找包含電影海報 upload/data 路徑的 <img>，取其 <table> 祖先。"""
    blocks = []
    seen_ids = set()

    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "upload/data" not in src:
            continue

        # 取包含完整電影資訊（含上映期間）的最近 <table> 祖先
        candidate = img.find_parent("table")
        if candidate is None:
            candidate = img.find_parent("tr")
        if candidate is None:
            continue

        block_id = id(candidate)
        if block_id not in seen_ids:
            seen_ids.add(block_id)
            blocks.append(candidate)

    return blocks


def _is_poster_image(src: str, img_tag) -> bool:
    """判斷此 <img> 是否為電影海報。"""
    if not src:
        return False
    src_lower = src.lower()
    # 排除明顯的非海報圖片（logo、icon、banner 等）
    exclude_keywords = ["logo", "icon", "banner", "button", "btn", "arrow", "bg", "background"]
    for kw in exclude_keywords:
        if kw in src_lower:
            return False
    # 海報圖片通常有一定尺寸，或在特定路徑下
    poster_keywords = ["poster", "movie", "film", "show", "pic", "img", "photo"]
    for kw in poster_keywords:
        if kw in src_lower:
            return True
    # 如果圖片有 width/height 屬性且尺寸合理（>80px），視為可能的海報
    width = img_tag.get("width", "")
    height = img_tag.get("height", "")
    try:
        if int(str(width).replace("px", "")) > 80:
            return True
    except (ValueError, TypeError):
        pass
    try:
        if int(str(height).replace("px", "")) > 100:
            return True
    except (ValueError, TypeError):
        pass
    # 副檔名為圖片格式且不在排除清單內
    if any(src_lower.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
        return True
    return False


def _fallback_find_movie_blocks(soup: BeautifulSoup) -> list:
    """備用策略：尋找含有特定關鍵字的文字區塊附近的內容。"""
    blocks = []
    # 尋找含有「上映」、「片長」、「分級」等關鍵字的 <td> 或 <div>
    keywords = ["上映", "片長", "分級", "場次"]
    for tag in soup.find_all(["td", "div", "p"]):
        text = tag.get_text()
        if any(kw in text for kw in keywords):
            parent = tag.find_parent("table") or tag.find_parent("div")
            if parent and parent not in blocks:
                blocks.append(parent)
    return blocks


def _parse_movie_block(block) -> dict:
    """從單一電影區塊解析電影詳細資訊。"""
    movie = {
        "name": "",
        "poster_url": "",
        "period": "",
        "rating": "",
        "duration": "",
        "showtimes": [],
        "raw_text": "",
    }

    # 電影名稱與海報 URL 從 upload/data 圖片的檔名取得
    for img in block.find_all("img"):
        src = img.get("src", "")
        if "upload/data" in src:
            # 保留原始 URL（含空格），供實際下載使用
            movie["poster_url"] = resolve_url(src)
            # 電影名稱去除前後空白
            movie["name"] = src.split("/")[-1].replace(".jpg", "").strip()
            break

    # 提取所有文字內容
    raw_text = block.get_text(separator="\n", strip=True)
    movie["raw_text"] = raw_text
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

    # 解析上映期間（如 4/3(五)~4/6(一)）
    period_pattern = re.compile(r"\d+/\d+(?:\([^)]+\))?[~～]\d+/\d+(?:\([^)]+\))?")
    for line in lines:
        m = period_pattern.search(line)
        if m:
            movie["period"] = m.group(0)
            break

    # 解析分級（取第一個 【XX】語言 格式）
    rating_pattern = re.compile(r"【\d+[普輔限護]】\S+")
    for line in lines:
        m = rating_pattern.search(line)
        if m:
            movie["rating"] = m.group(0)
            break

    # 解析片長（如 1時50分）
    duration_pattern = re.compile(r"(\d+)時(\d+)分")
    for line in lines:
        m = duration_pattern.search(line)
        if m:
            movie["duration"] = f"{m.group(1)}時{m.group(2)}分"
            break

    # 解析場次時間（全形冒號 ：）
    time_pattern = re.compile(r"\d{1,2}：\d{2}")
    showtimes = []
    seen = set()
    for line in lines:
        for t in time_pattern.findall(line):
            t_std = t.replace("：", ":")
            if t_std not in seen:
                seen.add(t_std)
                showtimes.append(t_std)
    movie["showtimes"] = showtimes

    return movie


def _expand_paired_movie(movie: dict) -> list[dict]:
    """
    若電影為組合片（片(一) 和 片(二) 名稱不同），拆為兩筆獨立記錄。
    從 raw_text 擷取各片名稱與分級；其餘欄位（海報、期間、片長、場次）共用。
    """
    lines = [l.strip() for l in movie.get("raw_text", "").split("\n") if l.strip()]

    # 找 片(一)/片(二) 後面的電影名稱
    part_names = {}
    part_ratings = {}
    i = 0
    rating_pattern = re.compile(r"【\d+[普輔限護]】\S+")
    rating_idx = 0
    all_ratings = [rating_pattern.search(l).group(0) for l in lines if rating_pattern.search(l)]

    while i < len(lines):
        line = lines[i]
        if line in ("片(一)", "片(二)"):
            part_key = line
            if i + 1 < len(lines):
                part_names[part_key] = lines[i + 1]
        i += 1

    name1 = part_names.get("片(一)", "")
    name2 = part_names.get("片(二)", "")

    # 只有兩片名稱不同時才拆分
    if not name1 or not name2 or name1 == name2:
        return [movie]

    rating1 = all_ratings[0] if len(all_ratings) > 0 else movie.get("rating", "")
    rating2 = all_ratings[1] if len(all_ratings) > 1 else movie.get("rating", "")

    base = {k: v for k, v in movie.items() if k not in ("name", "rating")}
    return [
        {**base, "name": name1, "rating": rating1},
        {**base, "name": name2, "rating": rating2},
    ]


def _is_metadata(text: str) -> bool:
    """判斷文字是否為元資料（非電影名稱）。"""
    meta_patterns = ["上映", "片長", "分級", "場次", "分鐘", "期間", "©", "UCC", "影城"]
    return any(p in text for p in meta_patterns)


def scrape_movies() -> list[dict]:
    """主入口：爬取 UCC 影城所有電影資訊。"""
    logger.info(f"開始爬取 UCC 影城網站：{TARGET_URL}")
    soup = fetch_page(TARGET_URL)
    if not soup:
        return []
    movies = extract_movies(soup)
    return movies


if __name__ == "__main__":
    movies = scrape_movies()
    import json
    print(json.dumps(movies, ensure_ascii=False, indent=2))
