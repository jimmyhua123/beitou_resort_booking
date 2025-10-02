# 北投會館爬蟲／台北捷運場地半自動預約器 – README

# 示範影片 https://www.youtube.com/watch?v=8dGmtffiORo

一個用 **Python + Selenium (undetected-chromedriver) + Tkinter** 製作的半自動搶場地工具，支援先開登入視窗完成驗證、Cloudflare 自動驗證等待與回彈、單/多分頁輪詢、時間與 A/B/C 場地篩選，以及一鍵前往「我的訂單」。

> 只操作你已登入的同一個瀏覽器實例；點擊時若遇到「驗證失敗」，會自動回彈等待 Cloudflare 通過後再重試。

---

## 目錄結構

```
beitou_resort_booking/
├─ app.py                # GUI 主程式（操作流程、按鈕、日誌）
├─ browser_cf.py         # 瀏覽器管理（UC）、Cloudflare 偵測/等待、輕量 stealth、暖身/回彈
├─ booking.py            # 直接點擊 place01/PlaceBtn（Step3Action），時間/場地過濾、確認彈窗處理
└─ uc_profile/           # UC 的使用者資料夾（首次登入後會建立，保存 Cookies）
```

---

## 需求與安裝

* Python 3.9+（3.10/3.11 亦可）
* Windows / macOS / Linux 皆可（Windows 會用 `winsound` 嗶聲，其他平台則印 `\a`）

安裝套件：

```bash
pip install undetected-chromedriver selenium python-dateutil
```

> 若公司/環境有限制自動下載 ChromeDriver，請確保本機 Chrome 能被 UC 自動管理；一般情況下不用額外設定。

---

## 快速開始

1. **啟動 GUI**

   ```bash
   python app.py
   ```

2. **按「開啟登入視窗（前往官方登入頁）」**
   會開啟 UC 瀏覽器並導向登入頁：
   `https://resortbooking.metro.taipei/MT02.aspx?module=login_page&files=login`
   在此視窗完成登入/驗證（Cookies 會保存於 `./uc_profile/`）。

3. **設定目標**

   * 日期（可多個，逗號分隔；格式 `YYYY/MM/DD` 或 `YYYY-MM-DD`）
   * 大時段 D2（可複選）

     * `1`＝09:00–12:00
     * `2`＝12:00–15:00
     * `3`＝15:00–18:00
     * `4`＝18:00–22:00
   * （選填）HH:MM 篩選：例如起 `19:00`、迄 `21:00`
   * （選填）限定場地 A / B / C（不勾＝全部）
   * 啟動模式：**立即**或**在指定時間 (HH:MM:SS)**
   * Cloudflare：**失敗最大重試**（建議 3–5）
   * 模式選擇：**單分頁模式（建議）**、**先到首頁暖身**（建議打勾）

4. **按「開始」**
   程式會依序開各目標頁，等待 Cloudflare 自動驗證通過，然後**直接點擊**每列「操作」欄位的可預約圖片（`place01.png` / `name=PlaceBtn`，`onclick` 含 `Step3Action(...)`），並自動按確認。若點擊當下出現「驗證失敗」，會回彈等待通過後**重試同一顆按鈕**。

5. **查看訂單**
   GUI 有「**我的訂單**」按鈕，可在同一個 UC 視窗開啟：
   `https://resortbooking.metro.taipei/MT02.aspx?module=member&files=orderx_mt`

---

## 核心功能說明

### 1) 開啟登入視窗（沿用同一瀏覽器）

* `app.py` 的「開啟登入視窗」使用 `browser_cf.BrowserManager.launch()` 啟動 UC，導向登入頁。
* 後續所有操作（預約/訂單/輪詢）都在**同一個** UC 視窗進行，沿用 Cookie。

### 2) Cloudflare 自動驗證（等待／回彈）

* `browser_cf.wait_until_ready_with_cf()` 會判斷：

  * `gate`（驗證中）：自動等待 + 模擬少量人為互動（滑鼠移動、滾動）
  * `success`（顯示成功橫幅）：自動隱藏橫幅避免遮擋
  * `fail`（例如 Error 1020 / Access denied）：**回彈**（先去首頁再回目標頁）或刷新，重試 N 次
* 點擊提交後若跳出 SweetAlert「驗證失敗」，`booking.py` 會回彈等待通過，再**重新定位同一顆**按鈕重試。

### 3) 直接點擊（不掃描表頭）

* 只鎖定 **操作欄**的可預約圖片（`place01.png` / `name=PlaceBtn`，且 `onclick` 含 `Step3Action`）。
* 從同列（或上列，處理 `rowspan`）解析起始時間（如 `18:00~19:00` 取 `18:00`），並抓場地文字（優先 `羽球A/B/C`）。
* 時間/場地過濾：若無設定或解析不到時間/場地，視為通過；有設定才比對。

### 4) 單分頁／多分頁

* **單分頁模式（推薦）**：同一分頁輪詢多個目標 URL，觸發驗證的機率較低。
* 多分頁模式：會分別開分頁，但 Cloudflare 可能較常觸發；程式已降低重複刷新頻率。

---

## 介面選項與建議

* **刷新間隔（秒）**：0.5–1.0s 之間較接近人類操作，過快易觸發驗證。
* **CF 失敗最大重試**：3–5；若網路不穩或常被判定，可再上調。
* **先到首頁暖身**：勾選後，在進入目標頁前先到官方首頁一次，有助降低初次請求就被攔。
* **單分頁模式**：建議保持開啟；需要同時搶很多頁面時再切換到多分頁模式。

---

## 常見問題（FAQ）

**Q1. 一點擊就跳「驗證失敗」？**
A：已內建回彈等待再重試。如果仍頻繁失敗：

* 將刷新間隔調慢（0.7–1.0s）
* 提高「CF 失敗最大重試」到 4–5
* 使用單分頁模式、勾選「先到首頁暖身」
* 避免同時間手動過度切換分頁或猛按 F5

**Q2. 找不到可預約按鈕？**
A：網站會用不同圖檔。預設鎖定 `place01.png` / `name=PlaceBtn` / `onclick` 含 `Step3Action`。
若你的頁面圖名不同，請提供 `img` 的 `src/name/onclick` 片段，我們可在 `booking.py` 的 XPath 擴充比對條件。

**Q3. 時間或場地判斷不準？**
A：表格常用 `rowspan`。目前邏輯會回看上列第一格時間，場地則優先抓含「羽球A/B/C」的格。若你要改成其他規則（例如「第1場/第2場」），可在 `booking.py` 中調整 `_row_court()` 的比對字串。

**Q4. 可以只列出有幾顆可預約再點嗎？**
A：目前已改為**直接點擊**；如果你想要掃描統計模式，我可以再提供帶「掃描不點擊」的分支版本。

---

## 進階設定

* **訂單快捷鍵**：「我的訂單」按鈕會導向
  `https://resortbooking.metro.taipei/MT02.aspx?module=member&files=orderx_mt`
  並同樣套用 Cloudflare 等待。
* **使用者資料夾**：UC 的 profile 在 `./uc_profile/`，刪除此資料夾相當於清除登入狀態。
* **程式日誌**：GUI 下方會持續輸出每輪狀態（已點擊、回彈、逾時等）。

---

## 注意事項

* 請遵守網站 **使用條款與公平使用原則**。此工具僅協助自動化你原本手動可完成的流程。
* 大量與高頻率請求可能觸發風控；**單分頁 + 合理間隔** 更穩定。
* 本程式不保證一定成功預約；成功與否仍取決於網站庫存、驗證策略與網路環境。

---

## 版本變更摘要

* **v1**：Remote Debug + 手動登入（已淘汰）
* **v2**：改用 UC、Cloudflare 三態偵測、掃描模式
* **v3**：新增「開啟登入視窗」、單分頁模式、暖身、直接點擊 `PlaceBtn/place01`
* **v4**：點擊後若驗證失敗 → 回彈等待 → 重新定位同一按鈕重試；新增「我的訂單」按鈕

---

## 授權

此專案僅供學術研究與個人自動化使用，請自行承擔使用風險並遵守所在地法規與網站條款。若要商用或二次散布，請先徵得原作者同意。
