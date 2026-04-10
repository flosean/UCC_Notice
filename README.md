# UCC 影城新電影自動偵測與 Telegram 通知系統

自動爬取 [UCC 影城](http://www.ucc-cinema.com.tw/main03.asp) 網站，偵測每週新上映電影，並透過 Telegram Bot 發送附海報的通知訊息。運行於 GitHub Actions，每天自動執行一次，無需自架伺服器。

## 功能特色

- 自動爬取 UCC 影城目前上映電影（名稱、海報、上映期間、分級、片長、場次）
- 比對歷史資料，僅通知**新上映**電影，避免重複推播
- 支援組合片（片(一)、片(二)）自動拆分為獨立通知
- 透過 Telegram Bot 發送**海報圖片 + 電影資訊**，無海報時自動降級為純文字
- 電影資料以 JSON 格式提交回 repository，自動保存歷史紀錄
- 支援手動觸發（`workflow_dispatch`）方便測試

## 系統架構

```
main.py          # 主流程，整合各模組
├── scraper.py   # 爬取 UCC 影城網頁，解析電影資訊
├── detector.py  # 比對歷史資料，偵測新電影
└── notifier.py  # 透過 Telegram Bot API 發送通知
```

電影資料存放於 `movies_data.json`，每次執行後由 GitHub Actions 自動提交更新。

## 部署方式

### 1. Fork 或 Clone 此 Repository

```bash
git clone https://github.com/<your-username>/UCC_Notice.git
cd UCC_Notice
```

### 2. 建立 Telegram Bot

1. 在 Telegram 搜尋 `@BotFather`，輸入 `/newbot` 建立新 Bot
2. 取得 **Bot Token**（格式如 `123456789:ABCdef...`）
3. 將 Bot 加入目標群組或頻道，並取得 **Chat ID**
   - 可使用 `@userinfobot` 查詢個人 Chat ID
   - 群組 Chat ID 通常為負數（如 `-1001234567890`）

### 3. 設定 GitHub Secrets

在 repository 的 **Settings → Secrets and variables → Actions** 新增：

| Secret 名稱 | 說明 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | 接收通知的 Chat ID |

### 4. 啟用 GitHub Actions

將 repository 推送至 GitHub 後，Actions 會依排程自動執行。首次執行時會將所有現有電影視為新電影並全數通知。

## 執行排程

GitHub Actions 設定每天 **台灣時間早上 09:00**（UTC 01:00）自動執行。

也可在 Actions 頁面點擊 **「Run workflow」** 手動觸發。

## 本地執行

### 安裝相依套件

```bash
pip install -r requirements.txt
```

### 設定環境變數

複製 `.env.example` 為 `.env` 並填入設定，或直接設定環境變數：

```bash
# Linux / macOS
export TELEGRAM_BOT_TOKEN=your_bot_token_here
export TELEGRAM_CHAT_ID=your_chat_id_here

# Windows PowerShell
$env:TELEGRAM_BOT_TOKEN="your_bot_token_here"
$env:TELEGRAM_CHAT_ID="your_chat_id_here"
```

### 執行

```bash
python main.py
```

## 通知訊息格式

每次偵測到新電影時，Bot 會先發送一則彙總訊息，再逐片發送：

```
🎥 UCC 影城 - 新電影通知
共有 N 部新電影上映！

🎬 電影名稱
📅 上映期間：4/10(五)~4/13(日)
🔞 分級：【12輔】國語
⏱ 片長：2時10分
🕐 場次：11:30　14:00　16:30　19:00
```

## 環境需求

- Python 3.11+
- 相依套件：`requests`、`beautifulsoup4`、`lxml`

## 授權

MIT License
