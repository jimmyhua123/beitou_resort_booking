# app.py
# GUI：保留「開啟登入視窗」與 Cloudflare 等待；移除掃描，直接在每頁連續點擊符合條件的〔預定場地〕。

import time
import threading
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, scrolledtext

from browser_cf import BrowserManager, LOGIN_URL, wait_until_ready_with_cf, HOME_URL,ORDER_URL
from booking import (
    parse_dates, parse_time_hhmm, build_urls,
    click_all_bookings_on_page
)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("台北捷運場地半自動預約器（直接點擊版）")
        self.geometry("980x680")

        self.browser = BrowserManager(profile_dir="uc_profile")
        self.stop_flag = threading.Event()
        self.worker_thread = None

        # 設定
        self.date_text = tk.StringVar()
        self.d2_1 = tk.IntVar(); self.d2_2 = tk.IntVar(); self.d2_3 = tk.IntVar(); self.d2_4 = tk.IntVar()
        self.from_t = tk.StringVar(); self.to_t = tk.StringVar()
        self.court_a = tk.IntVar(); self.court_b = tk.IntVar(); self.court_c = tk.IntVar()
        self.start_mode = tk.StringVar(value="now")
        self.start_time = tk.StringVar(value="23:59:55")
        self.interval = tk.StringVar(value="1.5")
        self.max_wait_min = tk.StringVar(value="8")
        self.cf_fail_retries = tk.StringVar(value="3")
        self.single_tab_mode = tk.IntVar(value=1)
        self.warmup_first   = tk.IntVar(value=1)

        self._build_ui()

    def _build_ui(self):
        pad = {'padx': 6, 'pady': 4}

        row0 = ttk.Frame(self); row0.pack(fill="x", **pad)
        ttk.Button(row0, text="開啟登入視窗（前往官方登入頁）", command=self.on_open_login).pack(side="left")
        ttk.Button(row0, text="我的訂單", command=self.on_open_orders).pack(side="left", padx=8)
        ttk.Label(row0, text="→ 請在新視窗完成登入/驗證，之後按『開始』").pack(side="left", padx=8)

        row1 = ttk.Frame(self); row1.pack(fill="x", **pad)
        ttk.Label(row1, text="日期（可多個，逗號分隔；2025/10/03 或 2025-10-03）").pack(anchor="w")
        ttk.Entry(row1, textvariable=self.date_text).pack(fill="x")

        row2 = ttk.Frame(self); row2.pack(fill="x", **pad)
        ttk.Label(row2, text="選擇大時段（D2）：1=09-12、2=12-15、3=15-18、4=18-22").pack(anchor="w")
        r2 = ttk.Frame(row2); r2.pack(anchor="w")
        ttk.Checkbutton(r2, text="1 (09-12)", variable=self.d2_1).pack(side="left")
        ttk.Checkbutton(r2, text="2 (12-15)", variable=self.d2_2).pack(side="left")
        ttk.Checkbutton(r2, text="3 (15-18)", variable=self.d2_3).pack(side="left")
        ttk.Checkbutton(r2, text="4 (18-22)", variable=self.d2_4).pack(side="left")

        row3 = ttk.Frame(self); row3.pack(fill="x", **pad)
        ttk.Label(row3, text="（可選）在大時段內再篩選 HH:MM 範圍（例如 19:00 → 21:00）").pack(anchor="w")
        r3 = ttk.Frame(row3); r3.pack(anchor="w")
        ttk.Label(r3, text="起").pack(side="left")
        ttk.Entry(r3, width=8, textvariable=self.from_t).pack(side="left")
        ttk.Label(r3, text="迄").pack(side="left")
        ttk.Entry(r3, width=8, textvariable=self.to_t).pack(side="left")

        row4 = ttk.Frame(self); row4.pack(fill="x", **pad)
        ttk.Label(row4, text="（可選）限定場地 A/B/C（不勾＝全部）").pack(anchor="w")
        r4 = ttk.Frame(row4); r4.pack(anchor="w")
        ttk.Checkbutton(r4, text="A 場", variable=self.court_a).pack(side="left")
        ttk.Checkbutton(r4, text="B 場", variable=self.court_b).pack(side="left")
        ttk.Checkbutton(r4, text="C 場", variable=self.court_c).pack(side="left")

        row5 = ttk.Frame(self); row5.pack(fill="x", **pad)
        ttk.Label(row5, text="啟動/刷新/驗證參數").pack(anchor="w")
        r5 = ttk.Frame(row5); r5.pack(anchor="w")
        ttk.Radiobutton(r5, text="立即開始", variable=self.start_mode, value="now").pack(side="left")
        ttk.Radiobutton(r5, text="在指定時間啟動 (HH:MM:SS)", variable=self.start_mode, value="at").pack(side="left")
        ttk.Entry(r5, width=10, textvariable=self.start_time).pack(side="left", padx=8)
        ttk.Label(r5, text="刷新間隔（秒）").pack(side="left")
        ttk.Entry(r5, width=8, textvariable=self.interval).pack(side="left", padx=(0,8))
        ttk.Label(r5, text="最大等待（分）").pack(side="left")
        ttk.Entry(r5, width=8, textvariable=self.max_wait_min).pack(side="left", padx=(0,8))
        ttk.Label(r5, text="CF 失敗最大重試").pack(side="left")
        ttk.Entry(r5, width=4, textvariable=self.cf_fail_retries).pack(side="left", padx=(0,12))
        ttk.Checkbutton(r5, text="單分頁模式（避免多開）", variable=self.single_tab_mode).pack(side="left", padx=(12,0))
        ttk.Checkbutton(r5, text="先到首頁暖身", variable=self.warmup_first).pack(side="left")

        row6 = ttk.Frame(self); row6.pack(fill="x", **pad)
        ttk.Button(row6, text="開始", command=self.on_start).pack(side="left")
        ttk.Button(row6, text="停止", command=self.on_stop).pack(side="left", padx=8)
        ttk.Button(row6, text="關閉", command=self.on_close).pack(side="left")

        self.logbox = scrolledtext.ScrolledText(self, height=22, wrap="word")
        self.logbox.pack(fill="both", expand=True, **pad)
        self._log("請先按『開啟登入視窗』→ 在 UC 瀏覽器登入；之後按『開始』。")

    # ---- Log ----
    def _log(self, s: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.logbox.insert("end", f"[{ts}] {s}\n")
        self.logbox.see("end")
        self.update_idletasks()

    # ---- Buttons ----
    def on_open_login(self):
        self.browser.launch(log=self._log, navigate_url=LOGIN_URL)
        self._log("已開啟 UC 瀏覽器登入頁；請在該視窗完成登入/驗證。")

    def on_open_orders(self):
        def _go():
            drv = self.browser.launch(log=self._log, navigate_url=ORDER_URL)
            self._log("前往『我的訂單』頁…")
            # 簡單等一下 CF 自動驗證；失敗會自動回彈再試
            wait_until_ready_with_cf(
                drv, target_url=ORDER_URL, max_wait=120, max_fail_retries=2,
                log=self._log, bounce_on_fail=True
            )
        threading.Thread(target=_go, daemon=True).start()
        

    def on_start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self._log("已有任務在跑，請先按【停止】。")
            return
        self.stop_flag.clear()
        self.worker_thread = threading.Thread(target=self.worker, daemon=True)
        self.worker_thread.start()

    def on_stop(self):
        self.stop_flag.set()
        self._log("已要求停止…")

    def on_close(self):
        self.stop_flag.set()
        self.destroy()

    # ---- Worker ----
    def worker(self):
        try:
            drv = self.browser.ensure_launched(log=self._log)

            dates = parse_dates(self.date_text.get())
            if not dates: self._log("請輸入至少一個日期。"); return
            d2_list = []
            if self.d2_1.get(): d2_list.append(1)
            if self.d2_2.get(): d2_list.append(2)
            if self.d2_3.get(): d2_list.append(3)
            if self.d2_4.get(): d2_list.append(4)
            if not d2_list: self._log("請至少勾選一個大時段（D2）。"); return

            from_t = parse_time_hhmm(self.from_t.get()) if self.from_t.get().strip() else None
            to_t   = parse_time_hhmm(self.to_t.get())   if self.to_t.get().strip()   else None
            want_A, want_B, want_C = bool(self.court_a.get()), bool(self.court_b.get()), bool(self.court_c.get())
            interval = float(self.interval.get() or "0.5")
            max_wait_min = float(self.max_wait_min.get() or "8")
            cf_fail_retries = int(self.cf_fail_retries.get() or "3")
            single_tab = bool(self.single_tab_mode.get())
            warmup = bool(self.warmup_first.get())

            urls = build_urls(dates, d2_list)
            self._log(f"目標頁面 {len(urls)} 個：")
            for u in urls: self._log(f"  {u}")

            # 定時啟動
            if self.start_mode.get() == "at":
                now = datetime.now()
                try: hh, mm, ss = map(int, self.start_time.get().split(":"))
                except Exception: self._log("指定時間格式錯誤，請用 HH:MM:SS"); return
                start_dt = now.replace(hour=hh, minute=mm, second=ss, microsecond=0)
                if start_dt <= now: start_dt += timedelta(days=1)
                self._log(f"等待至 {start_dt:%Y-%m-%d %H:%M:%S} 開始…")
                while not self.stop_flag.is_set() and datetime.now() < start_dt:
                    time.sleep(0.2)

            if single_tab:
                # 可先暖身一次
                if warmup:
                    drv.get(HOME_URL)
                    wait_until_ready_with_cf(drv, target_url=HOME_URL, max_wait=180, max_fail_retries=cf_fail_retries, log=self._log, bounce_on_fail=False)
                    time.sleep(0.4)

                deadline = datetime.now() + timedelta(minutes=max_wait_min)
                round_id = 0
                total_clicks = 0

                while not self.stop_flag.is_set() and datetime.now() < deadline:
                    round_id += 1
                    self._log(f"=== 單分頁輪詢第 {round_id} 回合 ===")
                    for url in urls:
                        if self.stop_flag.is_set(): break
                        drv.get(url)
                        ok = wait_until_ready_with_cf(drv, target_url=url, max_wait=240, max_fail_retries=cf_fail_retries, log=self._log, bounce_on_fail=True)
                        if not ok: 
                            self._log("  此頁仍未就緒，跳過。")
                            continue

                        clicked = click_all_bookings_on_page(    drv, from_t, to_t, want_A, want_B, want_C,    log_fn=self._log, max_click=999, cf_fail_retries=cf_fail_retries)
                        if clicked > 0:
                            total_clicks += clicked
                    time.sleep(interval)

                self._log(f"完成。此次總點擊 {total_clicks} 筆。")

            else:
                # 多分頁（保守刷新）
                tab_ready = {}; tab_last_check = {}
                for idx, url in enumerate(urls):
                    if self.stop_flag.is_set(): return
                    if idx == 0: drv.get(url)
                    else:
                        drv.switch_to.new_window('tab')
                        drv.get(url)
                    ok = wait_until_ready_with_cf(drv, target_url=url, max_wait=240, max_fail_retries=cf_fail_retries, log=self._log, bounce_on_fail=True)
                    h = drv.current_window_handle
                    tab_ready[h] = ok; tab_last_check[h] = time.time()
                    if not ok: self._log("此分頁等待驗證/載入逾時，稍後輪詢再試。")

                deadline = datetime.now() + timedelta(minutes=max_wait_min)
                round_id = 0
                total_clicks = 0
                stale_sec = 25

                while not self.stop_flag.is_set() and datetime.now() < deadline:
                    round_id += 1
                    self._log(f"=== 多分頁輪詢第 {round_id} 回合 ===")
                    for h in list(drv.window_handles):
                        if self.stop_flag.is_set(): break
                        try: drv.switch_to.window(h)
                        except Exception: continue

                        now_ts = time.time()
                        if not tab_ready.get(h, False):
                            ok = wait_until_ready_with_cf(drv, target_url=drv.current_url, max_wait=240, max_fail_retries=cf_fail_retries, log=self._log, bounce_on_fail=True)
                            tab_ready[h] = ok; tab_last_check[h] = now_ts
                            if not ok: self._log("  仍未通過驗證/載入，留待下輪。"); continue

                        clicked = click_all_bookings_on_page(drv, from_t, to_t, want_A, want_B, want_C, log_fn=self._log, max_click=999)
                        if clicked > 0:
                            total_clicks += clicked
                            tab_last_check[h] = now_ts
                            continue

                        if now_ts - tab_last_check.get(h, 0) > stale_sec:
                            try: drv.refresh()
                            except Exception: pass
                            ok = wait_until_ready_with_cf(drv, target_url=drv.current_url, max_wait=240, max_fail_retries=cf_fail_retries, log=self._log, bounce_on_fail=True)
                            tab_ready[h] = ok; tab_last_check[h] = time.time()

                    time.sleep(interval)

                self._log(f"完成。此次總點擊 {total_clicks} 筆。")

        except Exception as e:
            self._log(f"程式錯誤：{e}")
        finally:
            self._log("任務結束。")

if __name__ == "__main__":
    App().mainloop()
