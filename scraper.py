"""
網頁爬蟲模組 (Web Scraper Module)
訪問 UCC 影城新版網站，提取電影資訊與海報圖片 URL。
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import logging
import urllib3

# 停用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

TARGET_URL = "https://www.ucc-cinema.com.tw/product.html"
BASE_URL = "https://www.ucc-cinema.com.tw"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}


def fetch_page(url: str, max_retries: int = 3) -> BeautifulSoup | None:
    """發送 HTTP GET 請求並解析 HTML，對暫時性錯誤自動重試。"""
    for attempt in range(1, max_retries + 1):
        try:
            # 關閉 SSL 驗證以防 UCC 影城憑證設定有誤
            response = requests.get(url, headers=HEADERS, timeout=30, verify=False)
            response.raise_for_status()
            # 新版網站使用 UTF-8 編碼
            response.encoding = "utf-8"
            soup = BeautifulSoup(response.text, "html.parser")
            logger.info(f"成功取得頁面：{url}")
            return soup
        except requests.RequestException as e:
            logger.warning(f"取得頁面失敗（第 {attempt}/{max_retries} 次）{url}：{e}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)
    logger.error(f"無法取得頁面 {url}，已重試 {max_retries} 次")
    return None


def resolve_url(src: str) -> str:
    """將相對 URL 轉換為絕對 URL。"""
    if not src:
        return ""
    src = src.strip()
    if src.startswith("http://") or src.startswith("https://"):
        return src
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return BASE_URL + src
    return BASE_URL + "/" + src


def _parse_movie_detail(soup: BeautifulSoup, link: str) -> dict | None:
    """解析電影詳情頁資訊。"""
    movie = {
        "name": "",
        "poster_url": "",
        "period": "",
        "rating": "",
        "duration": "",
        "showtimes": [],
        "raw_text": "",
    }

    # 1. 電影名稱
    h1 = soup.find("div", class_="h1title")
    if h1 and h1.find("h1"):
        movie["name"] = h1.find("h1").get_text(strip=True)
    else:
        title = soup.find("title")
        if title:
            movie["name"] = title.get_text().split("-")[0].strip()

    if not movie["name"]:
        return None

    # 2. 海報圖片 URL (從 .detail-img 內提取)
    detail_img = soup.find(class_="detail-img")
    if detail_img:
        a_tag = detail_img.find("a", href=True)
        img_url = a_tag["href"] if a_tag else ""
        if not img_url:
            img_tag = detail_img.find("img", src=True)
            img_url = img_tag["src"] if img_tag else ""
        if img_url:
            img_url = img_url.split("?")[0]
            movie["poster_url"] = resolve_url(img_url)

    # 3. 規格與詳細介紹
    spec_div = soup.find(id="productSpec")
    desc_div = soup.find(id="productDesc")

    spec_text = spec_div.get_text(separator="\n", strip=True) if spec_div else ""
    desc_text = desc_div.get_text(separator="\n", strip=True) if desc_div else ""

    movie["raw_text"] = spec_text + "\n" + desc_text

    # 4. 解析上映期間
    period = ""
    if desc_div:
        # 匹配 7/3~7/9 格式
        period_pattern = re.compile(r"\d+/\d+(?:\([^)]+\))?[~～]\d+/\d+(?:\([^)]+\))?")
        m = period_pattern.search(desc_text)
        if m:
            period = m.group(0)
        else:
            # 匹配「上映時間：115 / 7/ 3」
            release_pattern = re.compile(r"上映時間：\s*(\d+\s*/\s*\d+\s*/\s*\d+)")
            m2 = release_pattern.search(spec_text)
            if m2:
                period = m2.group(1).replace(" ", "") + " 上映"
    movie["period"] = period

    # 5. 解析分級 (藉由圖片的 alt 屬性)
    rating_map = {
        "icon_g": "【0普】",
        "icon_p": "【6保】",
        "icon_pg12": "【12輔】",
        "icon_pg15": "【15輔】",
        "icon_r": "【18限】"
    }

    rating = ""
    if spec_div:
        for img in spec_div.find_all("img"):
            alt = img.get("alt", "")
            src = img.get("src", "")
            matched = False
            for key, val in rating_map.items():
                if key in alt or key in src:
                    rating = val
                    matched = True
                    break
            if matched:
                break

    # 解析語別
    lang = ""
    lang_match = re.search(r"語別：\s*(\S+)", spec_text)
    if lang_match:
        lang = lang_match.group(1)

    if rating:
        movie["rating"] = f"{rating}{lang}" if lang else rating
    else:
        movie["rating"] = f"【未知】{lang}" if lang else "【未知】"

    # 6. 解析片長
    dur_pat = re.search(r"(\d+)\s*時\s*(\d+)\s*分", spec_text + "\n" + desc_text)
    if dur_pat:
        movie["duration"] = f"{dur_pat.group(1)}時{dur_pat.group(2)}分"
    else:
        dur_pat2 = re.search(r"(\d+)\s*分", spec_text + "\n" + desc_text)
        if dur_pat2:
            movie["duration"] = f"{dur_pat2.group(1)}分"

    # 7. 解析場次時間
    showtimes = []
    if desc_div:
        time_pattern = re.compile(r"\d{1,2}[:：]\d{2}")
        seen = set()
        for td in desc_div.find_all("td"):
            text = td.get_text().strip()
            for t in time_pattern.findall(text):
                t_std = t.replace("：", ":")
                if t_std not in seen:
                    seen.add(t_std)
                    showtimes.append(t_std)
    movie["showtimes"] = showtimes

    return movie


def _expand_paired_movie(movie: dict) -> list[dict]:
    """
    若電影為組合片（片(一) 和 片(二) 名稱不同），拆為兩筆獨立記錄。
    相容於舊版設計與單元測試。
    """
    lines = [l.strip() for l in movie.get("raw_text", "").split("\n") if l.strip()]

    part_names = {}
    i = 0
    rating_pattern = re.compile(r"【\d+[普保護輔限]】\S+")
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

    if not name1 or not name2 or name1 == name2:
        return [movie]

    rating1 = all_ratings[0] if len(all_ratings) > 0 else movie.get("rating", "")
    rating2 = all_ratings[1] if len(all_ratings) > 1 else movie.get("rating", "")

    base = {k: v for k, v in movie.items() if k not in ("name", "rating")}
    return [
        {**base, "name": name1, "rating": rating1},
        {**base, "name": name2, "rating": rating2},
    ]


def extract_movies(soup: BeautifulSoup) -> list[dict]:
    """
    從解析後的 HTML 中提取所有電影資訊。
    採用兩階段解析法：
    1. 抓取 product.html 中的所有詳情連結。
    2. 對每個詳情頁解析出完整電影資訊。
    """
    product_list = soup.find(class_="product-list")
    if not product_list:
        logger.warning("未找到產品列表區塊")
        return []

    links = []
    for a in product_list.find_all("a", href=True):
        href = a["href"]
        if "product-detail-" in href:
            links.append(href)

    # 去重且保持順序
    seen_links = set()
    unique_links = []
    for link in links:
        if link not in seen_links:
            seen_links.add(link)
            unique_links.append(link)

    movies = []
    for link in unique_links:
        detail_url = resolve_url(link)
        logger.info(f"正在爬取電影詳情頁：{detail_url}")
        detail_soup = fetch_page(detail_url)
        if not detail_soup:
            continue

        movie = _parse_movie_detail(detail_soup, link)
        if not movie:
            continue

        # 過濾配片表或無效數據
        if "配片" in movie.get("name", "") or (not movie.get("period") and not movie.get("showtimes")):
            logger.info(f"  過濾無效項目：{movie.get('name')}")
            continue

        # 展開組合片（若有）
        expanded = _expand_paired_movie(movie)
        movies.extend(expanded)
        for m in expanded:
            logger.info(f"  解析電影：{m['name']}")
        time.sleep(0.5)

    logger.info(f"共解析到 {len(movies)} 部電影")
    return movies


def scrape_movies() -> list[dict]:
    """主入口：爬取 UCC 影城所有電影資訊。"""
    logger.info(f"開始爬取 UCC 影城網站：{TARGET_URL}")
    soup = fetch_page(TARGET_URL)
    if not soup:
        return []
    movies = extract_movies(soup)
    return movies


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    movies = scrape_movies()
    import json
    print(json.dumps(movies, ensure_ascii=False, indent=2))
