# browser_cf.py
# 管理 UC 瀏覽器 + Cloudflare 自動驗證偵測/等待 + 輕量 stealth + 失敗回彈

import os
import time
from typing import Optional, Callable
# --- Py3.12 distutils shim（必須放在 import undetected_chromedriver 之前）---
import sys, types, re
try:
    import distutils  # type: ignore
except ModuleNotFoundError:
    mod_distutils = types.ModuleType("distutils")
    mod_version = types.ModuleType("distutils.version")

    # 盡量模擬 LooseVersion；若安裝了 packaging 就用它比較，否則用簡單字串拆解比較
    try:
        from packaging.version import Version as _PkgVersion, InvalidVersion as _PkgInvalid
        class LooseVersion(_PkgVersion):  # type: ignore
            def __init__(self, v="0"):
                try:
                    super().__init__(str(v))
                except _PkgInvalid:
                    super().__init__(str(v).replace("_", "."))
    except Exception:
        class LooseVersion:  # 極簡比較，夠用於 uc 內部的版本判斷
            def __init__(self, v="0"):
                self.v = str(v)
            def _t(self):
                return [int(x) if x.isdigit() else x for x in re.split(r"[.\-]", self.v)]
            def __lt__(self, o): o = o if isinstance(o, LooseVersion) else LooseVersion(str(o)); return self._t() <  o._t()
            def __le__(self, o): o = o if isinstance(o, LooseVersion) else LooseVersion(str(o)); return self._t() <= o._t()
            def __eq__(self, o): o = o if isinstance(o, LooseVersion) else LooseVersion(str(o)); return self._t() == o._t()
            def __ne__(self, o): return not self == o
            def __gt__(self, o): return not self <= o
            def __ge__(self, o): return not self <  o

    mod_version.LooseVersion = LooseVersion
    sys.modules["distutils"] = mod_distutils
    sys.modules["distutils.version"] = mod_version
# --- End shim ---

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

LogFn = Callable[[str], None]

LOGIN_URL = "https://resortbooking.metro.taipei/MT02.aspx?module=login_page&files=login"
HOME_URL  = "https://resortbooking.metro.taipei/MT02.aspx?module=net_booking&files=booking_place&PT=1"
ORDER_URL = "https://resortbooking.metro.taipei/MT02.aspx?module=member&files=orderx_mt"

def _safe_exec_js(driver, js: str):
    try:
        driver.execute_script(js)
    except Exception:
        pass

def _inject_stealth(driver):
    js = r"""
    try {
      Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
      Object.defineProperty(navigator, 'languages', {get: () => ['zh-TW','zh','en-US','en']});
      Object.defineProperty(navigator, 'plugins',   {get: () => [1,2,3,4,5]});
      // chrome.runtime
      window.chrome = window.chrome || {};
      window.chrome.runtime = window.chrome.runtime || {};
      // WebGL spoof
      const getParameter = WebGLRenderingContext.prototype.getParameter;
      WebGLRenderingContext.prototype.getParameter = function(p){
        if (p === 37445) return 'Intel Inc.'; // UNMASKED_VENDOR_WEBGL
        if (p === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0)';
        return getParameter.apply(this, [p]);
      };
      // Permissions.query 調整（有些站會檢）
      const origQuery = (navigator.permissions && navigator.permissions.query) ? navigator.permissions.query.bind(navigator.permissions) : null;
      if (origQuery) {
        navigator.permissions.query = (p) => {
          if (p && p.name === 'notifications') return Promise.resolve({state: Notification.permission});
          return origQuery(p);
        };
      }
    } catch(e) {}
    """
    _safe_exec_js(driver, js)

class BrowserManager:
    def __init__(self, profile_dir: str = "uc_profile"):
        self.profile_dir = profile_dir
        self.driver = None

    def launch(self, log: LogFn = print, navigate_url: Optional[str] = None):
        """啟動 UC（如已啟動則重用）。第一次請在該視窗登入；Cookie 會保存在 profile_dir。"""
        if self.driver:
            if navigate_url:
                try:
                    self.driver.get(navigate_url)
                except Exception:
                    log("已開啟的瀏覽器導向失敗；請手動到登入頁。")
            return self.driver

        os.makedirs(self.profile_dir, exist_ok=True)
        opts = uc.ChromeOptions()
        opts.user_data_dir = os.path.abspath(self.profile_dir)
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--start-maximized")

        drv = uc.Chrome(options=opts, headless=False)
        drv.implicitly_wait(0.2)
        drv.set_page_load_timeout(60)
        self.driver = drv
        _inject_stealth(drv)

        if navigate_url:
            try:
                drv.get(navigate_url)
            except Exception:
                log("啟動後導向登入頁失敗；請手動輸入登入網址。")
        return drv

    def ensure_launched(self, log: LogFn = print):
        if not self.driver:
            raise RuntimeError("尚未啟動瀏覽器。請先按『開啟登入視窗』並完成登入/驗證。")
        return self.driver

    def quit(self):
        if self.driver:
            try: self.driver.quit()
            except Exception: pass
            self.driver = None


# ===== Cloudflare：三態 + 更嚴謹的「失敗」偵測 + 失敗回彈 =====

def get_cf_state(driver) -> str:
    """
    回傳：
      'gate'    驗證中（等待即可）
      'success' 顯示成功橫幅
      'fail'    真正的封鎖/失敗頁（1020/Access denied 等）
      'none'    無相關提示
    """
    try:
        # 真正的封鎖頁（更嚴謹，避免誤判）
        if driver.find_elements(By.XPATH, "//*[contains(., 'Error 1020') or contains(., 'error code: 1020') or contains(., 'Access denied') or contains(., '已封鎖')]"):
            return "fail"
        if driver.find_elements(By.XPATH, "//*[contains(@class,'cf-error') or contains(@id,'cf-error-details')]"):
            return "fail"

        # 驗證中
        if driver.find_elements(By.XPATH,
            "//*[contains(., 'Checking your browser') or contains(., '檢查您的瀏覽器') or contains(., '正在驗證') or contains(., '請稍候')]"
        ):
            return "gate"
        if driver.find_elements(By.XPATH,
            "//*[@id='challenge-stage' or contains(@class,'cf-browser-verification') or contains(@class,'challenge-form') or contains(@class,'challenge-platform')]"
        ):
            return "gate"
        if driver.find_elements(By.XPATH, "//iframe[contains(@src,'turnstile')]"):
            return "gate"

        # 成功橫幅
        if driver.find_elements(By.XPATH,
            "//*[contains(translate(., 'SUCCESS成功驗證完成', 'success成功驗證完成'), '成功') and contains(translate(., 'CLOUDFLARE', 'cloudflare'), 'cloudflare')]"
        ):
            return "success"
        if driver.find_elements(By.XPATH,
            "//*[contains(translate(., 'VERIFIED驗證完成', 'verified驗證完成'), '驗證完成') and contains(translate(., 'CLOUDFLARE', 'cloudflare'), 'cloudflare')]"
        ):
            return "success"
    except Exception:
        pass
    return "none"

def dismiss_cf_banner(driver):
    js = r"""
    try {
      const nodes = Array.from(document.querySelectorAll('body *'));
      for (const el of nodes) {
        const txt = (el.textContent || '').toLowerCase();
        if (txt.includes('cloudflare') && (txt.includes('成功') || txt.includes('success') || txt.includes('驗證完成'))) {
          const z = getComputedStyle(el).zIndex || '0';
          if (parseInt(z, 10) >= 10 || el.getBoundingClientRect().height < 160) {
            el.style.display = 'none';
          }
        }
      }
    } catch(e) {}
    """
    _safe_exec_js(driver, js)

def _simulate_human(driver, secs=1.2):
    """簡單的人為互動：移動滑鼠與滾動，降低 bot 味道。"""
    try:
        js = """
        (function(){
          const dx = 8 + Math.floor(Math.random()*20);
          const dy = 5 + Math.floor(Math.random()*16);
          const e = new MouseEvent('mousemove', {clientX: dx, clientY: dy, bubbles:true});
          document.body.dispatchEvent(e);
          window.scrollBy(0, Math.floor(20+Math.random()*60));
        })();
        """
        t0 = time.time()
        while time.time()-t0 < secs:
            _safe_exec_js(driver, js)
            time.sleep(0.25)
    except Exception:
        pass

def warmup_home_then_back(driver, target_url: str, log: LogFn):
    """先走一次 HOME（或 LOGIN）暖身，再回到目標 URL。"""
    try:
        log("↪️ 先前往首頁暖身後再回到目標頁…")
        driver.get(HOME_URL)
        _simulate_human(driver, secs=1.0)
        driver.get(target_url)
    except Exception:
        pass

def wait_until_ready_with_cf(driver, target_url: Optional[str]=None, max_wait: int = 240,
                             max_fail_retries: int = 3, log: LogFn = print,
                             bounce_on_fail: bool = True) -> bool:
    """
    自動等待 Cloudflare 完成驗證；顯示成功橫幅→隱藏；
    若偵測到真正失敗頁，最多重試 max_fail_retries 次（每次退避遞增），可選擇 bounce（去首頁或登入，再回來）。
    True = 表格/按鈕可用；False = 逾時/多次失敗。
    """
    fail_retries = 0
    t0 = time.time()
    while time.time() - t0 < max_wait:
        st = get_cf_state(driver)
        if st == "gate":
            _simulate_human(driver, secs=0.8)
            time.sleep(0.25)
            continue
        elif st == "success":
            dismiss_cf_banner(driver)

        elif st == "fail":
            if fail_retries < max_fail_retries:
                fail_retries += 1
                delay = min(2.0 * fail_retries, 8.0)
                log(f"⚠️ Cloudflare 阻擋（疑似 1020/Access denied），第 {fail_retries}/{max_fail_retries} 次回彈處理…")
                time.sleep(delay)
                if bounce_on_fail and target_url:
                    warmup_home_then_back(driver, target_url, log)
                else:
                    try: driver.refresh()
                    except Exception: pass
                t0 = time.time()
                continue
            else:
                log("❌ 多次失敗仍被阻擋。")
                return False

        # 檢查預定按鈕/表格
        if driver.find_elements(By.XPATH, "//table//img[@onclick]"):
            return True
        if driver.find_elements(By.XPATH, "//table"):
            time.sleep(0.15)
        else:
            time.sleep(0.15)

    log("⌛ 等待 Cloudflare/頁面載入逾時。")
    return False
