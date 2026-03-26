"""
UCC 影城新電影自動偵測與 Telegram 通知系統
主執行腳本 - 整合所有模組的運作流程。
"""

import logging
import sys
from scraper import scrape_movies
from detector import detect_new_movies, save_history
from notifier import notify_new_movies

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main() -> int:
    """
    主流程：
    1. 爬取 UCC 影城網站的電影資訊
    2. 與歷史資料比對，偵測新電影
    3. 對新電影發送 Telegram 通知
    4. 儲存最新電影資料

    Returns:
        0 表示成功，1 表示發生錯誤
    """
    logger.info("=" * 50)
    logger.info("UCC 影城新電影偵測系統 - 開始執行")
    logger.info("=" * 50)

    # 步驟 1：爬取電影資訊
    logger.info("【步驟 1/4】爬取 UCC 影城網站...")
    current_movies = scrape_movies()

    if not current_movies:
        logger.error("爬取失敗或網站無電影資訊，終止執行")
        return 1

    logger.info(f"成功取得 {len(current_movies)} 部電影資訊")

    # 步驟 2：偵測新電影
    logger.info("【步驟 2/4】比對歷史資料，偵測新電影...")
    new_movies = detect_new_movies(current_movies)

    if new_movies:
        logger.info(f"發現 {len(new_movies)} 部新電影：")
        for movie in new_movies:
            logger.info(f"  - {movie.get('name', '(未知)')}")
    else:
        logger.info("本次無新電影更新")

    # 步驟 3：發送 Telegram 通知
    logger.info("【步驟 3/4】發送 Telegram 通知...")
    if new_movies:
        try:
            notify_new_movies(new_movies)
        except ValueError as e:
            logger.error(f"通知設定錯誤：{e}")
            logger.error("請確認已設定 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID 環境變數")
            # 仍繼續儲存資料
        except Exception as e:
            logger.error(f"發送通知時發生未預期錯誤：{e}")
    else:
        logger.info("無新電影，跳過通知")

    # 步驟 4：儲存最新電影資料
    logger.info("【步驟 4/4】儲存最新電影資料...")
    success = save_history(current_movies)
    if not success:
        logger.error("儲存資料失敗")
        return 1

    logger.info("=" * 50)
    logger.info("執行完成")
    logger.info("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
