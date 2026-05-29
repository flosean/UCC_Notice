"""基本單元測試：驗證電影解析與新片偵測邏輯。

執行方式：
    pip install -r requirements-dev.txt
    pytest
"""

import detector
from scraper import _expand_paired_movie


def test_expand_paired_movie_splits_two_titles():
    """組合片應拆成兩筆，各自帶正確分級，並共用海報與期間。"""
    movie = {
        "name": "A&B",
        "poster_url": "http://x/A&B.jpg",
        "period": "5/1~5/3",
        "duration": "2時00分",
        "showtimes": ["10:00"],
        "rating": "",
        "raw_text": "A&B\n片(一)\n甲片\n片(二)\n乙片\n分級\n【6保】國語\n分級\n【12輔】英語",
    }
    result = _expand_paired_movie(movie)

    assert len(result) == 2
    assert {m["name"] for m in result} == {"甲片", "乙片"}
    assert all(m["poster_url"] == "http://x/A&B.jpg" for m in result)
    assert all(m["period"] == "5/1~5/3" for m in result)

    ratings = {m["name"]: m["rating"] for m in result}
    # 「保護級」(保) 過去因正則漏列而抓不到，這裡鎖定修正後的行為
    assert ratings["甲片"] == "【6保】國語"
    assert ratings["乙片"] == "【12輔】英語"


def test_expand_paired_movie_keeps_single_when_not_paired():
    """非組合片應原樣回傳單一筆。"""
    movie = {"name": "獨立片", "raw_text": "獨立片\n上映期間", "rating": "【0普】國語"}
    assert _expand_paired_movie(movie) == [movie]


def test_detect_accumulates_history(tmp_path, monkeypatch):
    """歷史採累積合併：部分爬取失敗後恢復，不應重複通知舊片。"""
    monkeypatch.setattr(detector, "DATA_FILE", tmp_path / "movies_data.json")

    day1 = [
        {"name": "甲", "period": "5/1~5/3"},
        {"name": "乙", "period": "5/1~5/3"},
    ]

    # 首次執行：全部視為新片
    assert len(detector.detect_new_movies(day1)) == 2
    detector.save_history(day1)

    # 第二天網站異常只抓到「甲」→ 累積合併應保留「乙」
    detector.save_history([{"name": "甲", "period": "5/1~5/3"}])

    # 第三天恢復正常，甲乙都在 → 因歷史已累積，兩者都不算新片
    assert detector.detect_new_movies(day1) == []

    # 真正的新檔期才會被通知
    day_new = [{"name": "丙", "period": "5/8~5/10"}]
    assert [m["name"] for m in detector.detect_new_movies(day_new)] == ["丙"]


def test_save_history_strips_raw_text(tmp_path, monkeypatch):
    """存檔時應移除 raw_text 以縮小 diff。"""
    import json

    data_file = tmp_path / "movies_data.json"
    monkeypatch.setattr(detector, "DATA_FILE", data_file)

    detector.save_history([
        {"name": "甲", "period": "5/1~5/3", "raw_text": "一大段原始文字", "duration": "2時00分"},
    ])

    saved = json.loads(data_file.read_text(encoding="utf-8"))
    record = saved["甲|5/1~5/3"]
    assert "raw_text" not in record
    assert record["duration"] == "2時00分"
