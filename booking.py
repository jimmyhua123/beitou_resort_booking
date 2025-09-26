# booking.py
# 直接在主表的「操作」欄點擊藍色〔預定場地〕圖片；可選時間/場地過濾

import re
import time
from typing import List

from dateutil import parser as dtparser
from selenium.webdriver.common.by import By
from selenium.webdriver.common.alert import Alert
from browser_cf import wait_until_ready_with_cf  # 用來回彈等待 CF

BASE_URL = (
    "https://resortbooking.metro.taipei/MT02.aspx"
    "?module=net_booking&files=booking_place&StepFlag=2&PT=1&D={date}&D2={d2}"
)

# --------- 參數解析 ---------
def parse_dates(text: str) -> List[str]:
    out = []
    if not text: return out
    for token in re.split(r"[,\s]+", text.strip()):
        if not token: continue
        dt = dtparser.parse(token).date()
        out.append(dt.strftime("%Y/%m/%d"))
    return out

def parse_time_hhmm(x):
    x = x.strip()
    if not x: return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", x)
    if not m: raise ValueError("時間格式應為 HH:MM")
    hh, mm = int(m.group(1)), int(m.group(2))
    if not (0 <= hh <= 23 and 0 <= mm <= 59): raise ValueError("時間超出 00:00~23:59")
    return f"{hh:02d}:{mm:02d}"

def build_urls(dates, d2_list):
    return [BASE_URL.format(date=d, d2=d2) for d in dates for d2 in d2_list]

# --------- 表格解析 & 點擊 ---------


# booking.py —— 直接點擊 PlaceBtn / place01.png 版


TIME_RANGE_RE = re.compile(r'([01]?\d|2[0-3]):[0-5]\d\s*[~～]\s*([01]?\d|2[0-3]):[0-5]\d')
START_TIME_RE = re.compile(r'([01]?\d|2[0-3]):[0-5]\d')

def _txt(el):
    try:
        return (el.text or '').strip()
    except Exception:
        return ''

def _find_placebtn_imgs(driver):
    # 只抓藍色可預約鈕（place01.png）或有 name=PlaceBtn，且 onclick 內含 Step3Action
    xp = ("//img[contains(@onclick,'Step3Action') and ("
          "@name='PlaceBtn' or contains(translate(@src,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'place01'))]")
    return driver.find_elements(By.XPATH, xp)

def _find_start_time_from_row_or_above(row):
    # 1) 先看本列第一格；2) 若沒時間（因 rowSpan 在上一列），往上找最近一列的第一格
    try:
        td1 = row.find_element(By.XPATH, "./td[1]")
        m = START_TIME_RE.search(_txt(td1))
        if m: return m.group(0)
    except Exception:
        pass
    try:
        prevs = row.find_elements(By.XPATH, "preceding-sibling::tr")
        for pr in reversed(prevs[-6:]):         # 回看最多 6 列就夠了（A/B/C 組）
            try:
                td1 = pr.find_element(By.XPATH, "./td[1]")
                m = START_TIME_RE.search(_txt(td1))
                if m: return m.group(0)
            except Exception:
                continue
    except Exception:
        pass
    return None

def _find_court_from_row(row):
    # 優先找包含「羽球」或 A/B/C 的格（且不是圖片的操作欄）
    try:
        cells = row.find_elements(By.XPATH, "./td")
        for c in cells:
            if c.find_elements(By.XPATH, ".//img"):   # 跳過操作欄
                continue
            t = _txt(c)
            if ('羽球' in t) or any(x in t for x in ('A','B','C')):
                return t
        if len(cells) >= 2:
            return _txt(cells[1])
    except Exception:
        pass
    return ""

def _handle_confirms(driver, sleep_s=0.05):
    # 1) JS alert/confirm
    try:
        a = Alert(driver)
        _ = a.text
        a.accept()
        time.sleep(sleep_s)
        return True
    except Exception:
        pass
    # 2) SweetAlert2（驗證失敗等）
    try:
        btns = driver.find_elements(By.CSS_SELECTOR, ".swal2-container .swal2-confirm")
        if btns:
            btns[0].click()
            time.sleep(sleep_s)
            return True
    except Exception:
        pass
    return False

# ====== 取代原本的 handle_any_confirm_popup，改為能辨識「驗證失敗」 ======
def _handle_confirm_and_detect_cf_fail(driver, timeout=3.0):
    """
    回傳:
      'ok'       : 已接受一般 confirm/alert 或無阻礙
      'cf_fail'  : 偵測到 SweetAlert/訊息包含「驗證失敗/請重新驗證」
      'none'     : 沒看到任何可處理的對話框
    """
    t0 = time.time()

    # 1) JS alert/confirm
    try:
        a = Alert(driver)
        _ = a.text  # 讀一次避免 NoAlertPresent
        a.accept()
        return 'ok'
    except Exception:
        pass

    # 2) SweetAlert2 之類的彈窗
    try:
        # 讀取標題或內容
        title_elems = driver.find_elements(By.CSS_SELECTOR, ".swal2-title")
        html_elems  = driver.find_elements(By.CSS_SELECTOR, ".swal2-html-container")
        text_all = " ".join([e.text for e in title_elems + html_elems]).strip()

        if text_all:
            lower = text_all.lower()
            if ("驗證失敗" in text_all) or ("重新驗證" in text_all) or ("verification failed" in lower):
                # 點「確定」把彈窗關掉
                btns = driver.find_elements(By.CSS_SELECTOR, ".swal2-container .swal2-confirm")
                if btns: btns[0].click()
                return 'cf_fail'

        # 若只是一般提示，也把「確定」按掉
        btns = driver.find_elements(By.CSS_SELECTOR, ".swal2-container .swal2-confirm")
        if btns:
            btns[0].click()
            return 'ok'
    except Exception:
        pass

    return 'none'


# ====== 取代原本的 click_all_bookings_on_page：加入 CF 失敗回彈重試 ======
def click_all_bookings_on_page(driver, from_t, to_t, want_A, want_B, want_C,
                               log_fn=None, max_click=999, cf_fail_retries=3):
    """
    直接在「操作」欄點擊藍色〔預定場地〕圖片；若點擊後出現「驗證失敗」，
    會自動回彈等待 Cloudflare 通過，再重新定位同一按鈕重試（最多 cf_fail_retries 次）。
    """
    # 只抓藍色可預約鈕（place01 / name=PlaceBtn）且 onclick 含 Step3Action
    imgs = driver.find_elements(
        By.XPATH,
        "//img[contains(@onclick,'Step3Action') and "
        "(@name='PlaceBtn' or contains(translate(@src,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'place01'))]"
    )
    if log_fn:
        log_fn(f"  🔵 找到可預約按鈕 {len(imgs)} 顆，開始點擊…")

    def _row_time(row):
        # 取本列或上一列第一格的起始時間（處理 rowspan）
        try:
            td1 = row.find_element(By.XPATH, "./td[1]")
            m = re.search(r'([01]?\d|2[0-3]):[0-5]\d', td1.text or '')
            if m: return m.group(0)
        except Exception:
            pass
        try:
            prev = row.find_element(By.XPATH, "preceding-sibling::tr[1]")
            td1  = prev.find_element(By.XPATH, "./td[1]")
            m = re.search(r'([01]?\d|2[0-3]):[0-5]\d', td1.text or '')
            if m: return m.group(0)
        except Exception:
            pass
        return None

    def _row_court(row):
        try:
            cells = row.find_elements(By.XPATH, "./td")
            for c in cells:
                if c.find_elements(By.XPATH, ".//img"):  # 跳過操作欄
                    continue
                t = (c.text or '').strip()
                if ('羽球' in t) or any(x in t for x in ('A','B','C')):
                    return t
            if len(cells) >= 2:
                return (cells[1].text or '').strip()
        except Exception:
            pass
        return ""

    clicked = 0

    for img in imgs:
        if clicked >= max_click: break

        # 對應列資訊
        try:
            row = img.find_element(By.XPATH, "./ancestor::tr[1]")
        except Exception:
            row = None
        t_text = _row_time(row) if row is not None else None
        c_text = _row_court(row) if row is not None else ""

        # 時間/場地篩選
        time_ok = True
        if (from_t or to_t) and t_text:
            if from_t and t_text < from_t: time_ok = False
            if to_t   and t_text > to_t:   time_ok = False
        court_ok = True
        if any([want_A, want_B, want_C]):
            up = (c_text or "").upper()
            court_ok = (want_A and 'A' in up) or (want_B and 'B' in up) or (want_C and 'C' in up)
        if not (time_ok and court_ok):
            continue

        # 解析 onclick 參數，供重試時重新定位同一顆
        oc = img.get_attribute("onclick") or ""
        m  = re.search(r"Step3Action\((\d+)\s*,\s*(\d+)\)", oc)
        sel_same = None
        if m:
            sel_same = f"//img[contains(@onclick,'Step3Action({m.group(1)},{m.group(2)})')]"

        # 進行點擊 + 必要時的回彈重試
        attempts = 0
        while attempts <= cf_fail_retries:
            attempts += 1
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", img)
                time.sleep(0.12)  # 給一點人為延遲
                img.click()
                time.sleep(0.10)

                status = _handle_confirm_and_detect_cf_fail(driver, timeout=2.0)
                if status != 'cf_fail':
                    # ok / none 都算完成一次點擊
                    clicked += 1
                    if log_fn:
                        log_fn(f"  ✅ 點擊完成：時間『{t_text or '?'}』 場地『{c_text or '?'}』"
                               + ("" if attempts==1 else f"（重試{attempts-1}次）"))
                    break

                # ----- 走到這裡表示「驗證失敗」：回彈等待，再重找同一顆重新點 -----
                if log_fn: log_fn("   ⏳ 驗證失敗→回彈等待 Cloudflare 通過後重試…")
                ok = wait_until_ready_with_cf(driver, target_url=driver.current_url,
                                              max_wait=240, max_fail_retries=3,
                                              log=(log_fn or print), bounce_on_fail=True)
                if not ok:
                    if log_fn: log_fn("   ❌ 回彈後仍未通過，放棄此按鈕。")
                    break

                # 重新定位同一顆
                if sel_same:
                    found = driver.find_elements(By.XPATH, sel_same)
                    if not found:
                        if log_fn: log_fn("   ❌ 回彈後找不到同一按鈕，放棄此按鈕。")
                        break
                    img = found[0]
                # 迴圈會自動重試
            except Exception as e:
                if log_fn: log_fn(f"   ⚠️ 點擊失敗：{e}")
                break

    if log_fn and clicked == 0:
        log_fn("  （沒有成功點擊任何項目，可能都被佔用或持續被驗證擋下）")
    return clicked
