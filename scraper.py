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
        if movie and movie.get("name"):
            movies.append(movie)
            logger.info(f"  解析電影：{movie['name']}")

    logger.info(f"共解析到 {len(movies)} 部電影")
    return movies


def _find_movie_blocks(soup: BeautifulSoup) -> list:
    """主要解析策略：尋找包含電影海報的區塊，取 <tr> 或內層 <table> 以涵蓋文字與圖片。"""
    blocks = []
    seen_ids = set()

    all_imgs = soup.find_all("img")
    for img in all_imgs:
        src = img.get("src", "")
        if not _is_poster_image(src, img):
            continue

        # 優先取包含圖片的 <tr>（海報與文字通常並排在同一 <tr> 內）
        # 再往上找較小的包裝 <table>，避免取到最外層大 table
        candidate = None
        for ancestor in img.parents:
            tag_name = getattr(ancestor, "name", None)
            if tag_name == "tr":
                candidate = ancestor
                break
            if tag_name == "table":
                candidate = ancestor
                break

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

    # 提取海報圖片 URL
    imgs = block.find_all("img")
    for img in imgs:
        src = img.get("src", "")
        if _is_poster_image(src, img):
            movie["poster_url"] = resolve_url(src)
            break

    # 提取所有文字內容
    raw_text = block.get_text(separator="\n", strip=True)
    movie["raw_text"] = raw_text
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

    # 解析電影名稱（通常是第一行較長的文字，或帶有特定樣式的標題）
    # 優先查找 <b>、<strong>、<h*> 等強調標籤
    for tag in block.find_all(["b", "strong", "h1", "h2", "h3", "h4", "font"]):
        text = tag.get_text(strip=True)
        if text and len(text) > 1 and not _is_metadata(text):
            movie["name"] = text
            break

    # 若找不到強調標籤，用第一行非元資料文字當作電影名稱
    if not movie["name"]:
        for line in lines:
            if len(line) > 1 and not _is_metadata(line):
                movie["name"] = line
                break

    # 解析上映期間
    period_pattern = re.compile(r"(\d{1,4}[/-]\d{1,2}[/-]\d{1,4})")
    for line in lines:
        if "上映" in line or "期間" in line or "日期" in line:
            dates = period_pattern.findall(line)
            if dates:
                movie["period"] = " ~ ".join(dates[:2])
            else:
                # 直接取該行去掉標籤後的內容
                movie["period"] = re.sub(r"[上映期間：:]", "", line).strip()
            break

    # 解析分級
    rating_keywords = ["輔導", "普通", "限制", "保護", "輔12", "輔15", "護"]
    for line in lines:
        if "分級" in line or "級" in line:
            for kw in rating_keywords:
                if kw in line:
                    movie["rating"] = kw
                    break
            if not movie["rating"]:
                movie["rating"] = re.sub(r"[分級：:]", "", line).strip()
            break

    # 解析片長
    duration_pattern = re.compile(r"(\d+)\s*分")
    for line in lines:
        if "片長" in line or "分鐘" in line or "分" in line:
            m = duration_pattern.search(line)
            if m:
                movie["duration"] = f"{m.group(1)} 分鐘"
                break

    # 解析場次時間
    time_pattern = re.compile(r"\d{1,2}:\d{2}")
    showtimes = []
    for line in lines:
        times = time_pattern.findall(line)
        showtimes.extend(times)
    movie["showtimes"] = list(dict.fromkeys(showtimes))  # 去重並保持順序

    return movie


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
