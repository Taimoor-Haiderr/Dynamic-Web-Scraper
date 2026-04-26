import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import json
import csv
import os
import re
import datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd


# ──────────────────────────────────────────────
#  COLOURS
# ──────────────────────────────────────────────
C = {
    "bg":        "#0D0D0D",
    "panel":     "#161616",
    "card":      "#111111",
    "input":     "#1E1E1E",
    "border":    "#2C2C2C",
    "red":       "#D91A2A",
    "red_dark":  "#8B0000",
    "red_hover": "#B01020",
    "white":     "#F0F0F0",
    "grey":      "#888888",
    "grey_d":    "#444444",
    "green":     "#2ECC71",
    "yellow":    "#F0A500",
    "error":     "#E74C3C",
    "text":      "#E8E8E8",
    "text_dim":  "#999999",
}

# ──────────────────────────────────────────────
#  HTTP HEADERS
# ──────────────────────────────────────────────
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
}


# ──────────────────────────────────────────────
#  UTILITY
# ──────────────────────────────────────────────
def safe_get(url, timeout=14):
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except requests.exceptions.Timeout:
        raise ConnectionError(f"Timeout: {url}")
    except requests.exceptions.ConnectionError:
        raise ConnectionError(f"Connection failed: {url}")
    except requests.exceptions.HTTPError as e:
        raise ConnectionError(f"HTTP {e.response.status_code}: {url}")
    except Exception as e:
        raise ConnectionError(str(e))


def clean(text):
    if not text:
        return "N/A"
    return re.sub(r'\s+', ' ', str(text)).strip()


def timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


# ──────────────────────────────────────────────
#  SCRAPER — JOBS
# ──────────────────────────────────────────────
def scrape_jobs(url, pages, log):
    results = []
    log(f"Connecting: {url}", "info")
    try:
        r = safe_get(url)
        ct = r.headers.get("Content-Type", "")

        if "json" in ct or url.endswith("/api") or url.endswith(".json"):
            data = r.json()
            items = [d for d in data if isinstance(d, dict) and d.get("position")]
            for job in items[:40 * pages]:
                results.append({
                    "Title":      clean(job.get("position")),
                    "Company":    clean(job.get("company")),
                    "Location":   clean(job.get("location") or "Remote"),
                    "Tags":       ", ".join(job.get("tags", [])[:5]),
                    "Salary":     clean(job.get("salary") or "Not specified"),
                    "Date":       clean(str(job.get("date", ""))[:10]),
                    "Apply Link": f"https://remoteok.com/remote-jobs/{job.get('id','')}",
                    "Source":     url,
                })
            log(f"Extracted {len(results)} jobs from JSON.", "success")

        else:
            for page in range(1, pages + 1):
                page_url = url if page == 1 else f"{url.rstrip('/')}/page/{page}"
                log(f"Page {page}: {page_url}", "info")
                try:
                    rp   = safe_get(page_url)
                    soup = BeautifulSoup(rp.text, "html.parser")
                    cards = (soup.select("article") or
                             soup.select("[class*='job']") or
                             soup.select("[class*='listing']"))
                    for card in cards[:30]:
                        t = card.find(["h2", "h3", "h4", "a"])
                        c = card.find(class_=re.compile("company|employer", re.I))
                        l = card.find(class_=re.compile("location|city", re.I))
                        a = card.find("a", href=True)
                        link = ""
                        if a:
                            href = a["href"]
                            link = href if href.startswith("http") else url.rstrip("/") + "/" + href.lstrip("/")
                        results.append({
                            "Title":      clean(t.get_text() if t else "N/A"),
                            "Company":    clean(c.get_text() if c else "N/A"),
                            "Location":   clean(l.get_text() if l else "N/A"),
                            "Tags":       "",
                            "Salary":     "N/A",
                            "Date":       datetime.date.today().isoformat(),
                            "Apply Link": link,
                            "Source":     page_url,
                        })
                    log(f"Page {page}: {len(cards)} records.", "success")
                except Exception as e:
                    log(f"Page {page} error: {e}", "warning")
    except Exception as e:
        log(f"Jobs error: {e}", "error")
    return results


# ──────────────────────────────────────────────
#  SCRAPER — PRODUCTS
# ──────────────────────────────────────────────
def scrape_products(url, pages, log):
    results = []
    log(f"Connecting: {url}", "info")
    try:
        r  = safe_get(url)
        ct = r.headers.get("Content-Type", "")

        if "json" in ct:
            items = r.json()
            if not isinstance(items, list):
                items = [items]
            for p in items:
                rating = p.get("rating", "N/A")
                if isinstance(rating, dict):
                    rating = rating.get("rate", "N/A")
                results.append({
                    "Name":         clean(p.get("title") or p.get("name")),
                    "Price":        f"${p.get('price', 'N/A')}",
                    "Rating":       str(rating),
                    "Category":     clean(p.get("category")),
                    "Description":  clean(str(p.get("description", ""))[:120]),
                    "Product Link": url,
                    "Source":       url,
                })
            log(f"Extracted {len(results)} products (JSON).", "success")

        else:
            for page in range(1, pages + 1):
                if "page-" in url:
                    page_url = re.sub(r'page-\d+', f'page-{page}', url)
                elif page == 1:
                    page_url = url
                else:
                    page_url = f"{url.rstrip('/')}/page-{page}.html"

                log(f"Page {page}: {page_url}", "info")
                try:
                    rp   = safe_get(page_url)
                    soup = BeautifulSoup(rp.text, "html.parser")

                    articles = soup.select("article.product_pod")
                    if articles:
                        rating_map = {"One": "1", "Two": "2", "Three": "3",
                                      "Four": "4", "Five": "5"}
                        for art in articles:
                            name_el  = art.select_one("h3 a")
                            price_el = art.select_one(".price_color")
                            star_el  = art.select_one("p.star-rating")
                            star_cls = star_el["class"][1] if star_el else "N/A"
                            href     = name_el["href"].replace("../", "") if name_el else ""
                            results.append({
                                "Name":         clean(name_el.get("title") if name_el else "N/A"),
                                "Price":        clean(price_el.text if price_el else "N/A"),
                                "Rating":       rating_map.get(star_cls, star_cls),
                                "Category":     "Books",
                                "Description":  "Visit product page for details.",
                                "Product Link": f"https://books.toscrape.com/catalogue/{href}",
                                "Source":       page_url,
                            })
                        log(f"Page {page}: {len(articles)} products.", "success")
                    else:
                        cards = (soup.select("[class*='product']") or
                                 soup.select("[class*='item']") or
                                 soup.select("[class*='card']"))
                        for card in cards[:30]:
                            n = card.find(["h2", "h3", "h4", "a"])
                            pr = card.find(class_=re.compile("price|cost", re.I))
                            a  = card.find("a", href=True)
                            link = ""
                            if a:
                                href = a["href"]
                                link = href if href.startswith("http") else url.rstrip("/") + "/" + href.lstrip("/")
                            results.append({
                                "Name":         clean(n.get_text() if n else "N/A"),
                                "Price":        clean(pr.get_text() if pr else "N/A"),
                                "Rating":       "N/A",
                                "Category":     "N/A",
                                "Description":  "N/A",
                                "Product Link": link,
                                "Source":       page_url,
                            })
                        log(f"Page {page}: {len(cards)} items (generic).", "success")
                except Exception as e:
                    log(f"Page {page} error: {e}", "warning")
    except Exception as e:
        log(f"Products error: {e}", "error")
    return results


# ──────────────────────────────────────────────
#  SCRAPER — NEWS
# ──────────────────────────────────────────────
def scrape_news(url, pages, log):
    results = []
    log(f"Connecting: {url}", "info")
    try:
        r  = safe_get(url)
        ct = r.headers.get("Content-Type", "")

        if "json" in ct:
            data = r.json()
            if isinstance(data, list) and data and isinstance(data[0], int):
                ids     = data[:25 * pages]
                fetched = 0
                for sid in ids:
                    if fetched >= 30:
                        break
                    try:
                        ri = safe_get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
                        d  = ri.json()
                        if d and d.get("type") == "story" and d.get("title"):
                            results.append({
                                "Title":       clean(d.get("title")),
                                "Source":      "HackerNews",
                                "Published":   datetime.datetime.utcfromtimestamp(
                                               d.get("time", 0)).strftime("%Y-%m-%d %H:%M"),
                                "Category":    "Tech",
                                "Score":       str(d.get("score", 0)),
                                "Comments":    str(d.get("descendants", 0)),
                                "Description": clean(BeautifulSoup(
                                               d.get("text", ""), "html.parser").get_text())[:180],
                                "Link":        d.get("url") or
                                               f"https://news.ycombinator.com/item?id={sid}",
                            })
                            fetched += 1
                    except Exception:
                        pass
                log(f"Extracted {fetched} stories (HackerNews API).", "success")
            else:
                log("JSON format not recognised. Try an RSS or HTML news URL.", "warning")

        elif "xml" in ct or url.endswith(".rss") or url.endswith(".xml"):
            rp   = safe_get(url)
            soup = BeautifulSoup(rp.text, "xml")
            for entry in soup.find_all(["entry", "item"])[:40 * pages]:
                t   = entry.find("title")
                lnk = entry.find("link")
                pub = entry.find(["published", "pubDate", "updated"])
                dsc = entry.find(["summary", "description", "content"])
                src = entry.find("source")
                link_val = ""
                if lnk:
                    link_val = lnk.get("href") or lnk.get_text(strip=True)
                desc_val = ""
                if dsc:
                    desc_val = BeautifulSoup(dsc.get_text(), "html.parser").get_text()[:200]
                results.append({
                    "Title":       clean(t.get_text() if t else "N/A"),
                    "Source":      clean(src.get_text() if src else url),
                    "Published":   clean(pub.get_text()[:16] if pub else "N/A"),
                    "Category":    "News",
                    "Score":       "N/A",
                    "Comments":    "N/A",
                    "Description": clean(desc_val),
                    "Link":        link_val,
                })
            log(f"Extracted {len(results)} articles (RSS).", "success")

        else:
            for page in range(1, pages + 1):
                page_url = url if page == 1 else f"{url.rstrip('/')}?page={page}"
                log(f"Page {page}: {page_url}", "info")
                try:
                    rp   = safe_get(page_url)
                    soup = BeautifulSoup(rp.text, "html.parser")
                    arts = (soup.select("article") or
                            soup.select("[class*='story']") or
                            soup.select("[class*='article']"))
                    for art in arts[:30]:
                        t  = art.find(["h1", "h2", "h3", "h4"])
                        a  = art.find("a", href=True)
                        p  = art.find(["p", "div"],
                                      class_=re.compile("desc|summary|excerpt", re.I))
                        tm = art.find(["time", "span"],
                                      class_=re.compile("date|time|publish", re.I))
                        link = ""
                        if a:
                            href = a["href"]
                            link = href if href.startswith("http") else url.rstrip("/") + "/" + href.lstrip("/")
                        results.append({
                            "Title":       clean(t.get_text() if t else "N/A"),
                            "Source":      url,
                            "Published":   clean(tm.get_text() if tm else
                                           datetime.date.today().isoformat()),
                            "Category":    "News",
                            "Score":       "N/A",
                            "Comments":    "N/A",
                            "Description": clean(p.get_text() if p else "N/A")[:180],
                            "Link":        link,
                        })
                    log(f"Page {page}: {len(arts)} articles.", "success")
                except Exception as e:
                    log(f"Page {page} error: {e}", "warning")
    except Exception as e:
        log(f"News error: {e}", "error")
    return results


# ──────────────────────────────────────────────
#  MAIN APPLICATION
# ──────────────────────────────────────────────
class App(tk.Tk):

    COLUMNS = {
        "Jobs":     ["Title", "Company", "Location",  "Salary", "Date",  "Source"],
        "Products": ["Name", "Price", "Rating", "Category", "Description", "Product Link", "Source"],
        "News":     ["Title", "Source", "Published", "Category","Description", "Link"],
    }
    COL_W = {
        "Title": 210, "Company": 140, "Location": 110, "Tags": 130,
        "Salary": 100, "Date": 90, "Apply Link": 220, "Source": 130,
        "Name": 220, "Price": 75, "Rating": 60, "Category": 100,
        "Description": 250, "Product Link": 220,
        "Published": 130, "Score": 55, "Comments": 65, "Link": 220,
    }

    def __init__(self):
        super().__init__()
        self.title("Dynamic Web Scraper ")
        self.geometry("1320x800")
        self.minsize(1000, 650)
        self.configure(bg=C["bg"])
        self.resizable(True, True)

        self.data          = []
        self.filtered_data = []
        self.category_var  = tk.StringVar(value="Jobs")
        self.search_var    = tk.StringVar()
        self.pages_var     = tk.StringVar(value="2")
        self.url_var       = tk.StringVar(value="")
        self.status_var    = tk.StringVar(value="Ready")
        self.scraping      = False
        self._sort_col     = None
        self._sort_rev     = False
        self._cat_btns     = {}

        self._setup_styles()
        self._build_ui()
        self._tick_clock()

    # ── Styles ────────────────────────────────
    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure("Treeview",
            background=C["card"], foreground=C["text"],
            fieldbackground=C["card"], rowheight=28,
            borderwidth=0, relief="flat",
            font=("Helvetica", 10))
        s.configure("Treeview.Heading",
            background=C["red_dark"], foreground=C["white"],
            font=("Helvetica", 9, "bold"), relief="flat",
            borderwidth=0)
        s.map("Treeview",
            background=[("selected", C["red_dark"])],
            foreground=[("selected", C["white"])])
        s.map("Treeview.Heading",
            background=[("active", C["red_hover"])])

        s.configure("TScrollbar",
            background=C["panel"], troughcolor=C["bg"],
            arrowcolor=C["grey_d"], borderwidth=0)

        s.configure("TProgressbar",
            background=C["red"], troughcolor=C["panel"],
            borderwidth=0)

    # ── Build UI ──────────────────────────────
    def _build_ui(self):
        self._build_header()
        tk.Frame(self, bg=C["red"], height=2).pack(fill="x")

        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=12, pady=10)

        self._build_sidebar(body)
        self._build_main_area(body)
        self._build_statusbar()

    # ── Header ────────────────────────────────
    def _build_header(self):
        hdr = tk.Frame(self, bg=C["bg"], height=58)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        lf = tk.Frame(hdr, bg=C["bg"])
        lf.pack(side="left", padx=20, pady=8)

        tk.Label(lf, text="WEB SCRAPER ",
                 font=("Georgia", 18, "bold"),
                 fg=C["red"], bg=C["bg"]).pack(anchor="w")

        tk.Label(lf, text="Real-Time Data Extraction  |  Jobs  |  Products  |  News",
                 font=("Helvetica", 9),
                 fg=C["grey"], bg=C["bg"]).pack(anchor="w")

        self.clock_lbl = tk.Label(hdr, font=("Courier", 10),
                                  fg=C["grey_d"], bg=C["bg"])
        self.clock_lbl.pack(side="right", padx=20)

    # ── Sidebar ───────────────────────────────
    def _build_sidebar(self, parent):
        sb = tk.Frame(parent, bg=C["panel"], width=218,
                      highlightbackground=C["border"], highlightthickness=1)
        sb.pack(side="left", fill="y", padx=(0, 10))
        sb.pack_propagate(False)

        def sec(title):
            tk.Label(sb, text=title,
                     font=("Helvetica", 8, "bold"),
                     fg=C["red"], bg=C["panel"],
                     anchor="w").pack(fill="x", padx=14, pady=(12, 2))
            tk.Frame(sb, bg=C["border"], height=1).pack(fill="x", padx=14, pady=(0, 6))

        # ── Category ──
        sec("CATEGORY")
        for cat in ["Jobs", "Products", "News"]:
            b = tk.Button(sb, text=cat,
                font=("Helvetica", 10, "bold"),
                bg=C["input"], fg=C["grey"],
                relief="flat", anchor="w",
                padx=14, pady=7, cursor="hand2",
                activebackground=C["red_dark"],
                activeforeground=C["white"],
                bd=0, highlightthickness=0,
                command=lambda c=cat: self._select_cat(c))
            b.pack(fill="x", padx=10, pady=2)
            self._cat_btns[cat] = b
        self._select_cat("Jobs")

        # ── URL ──
        sec("TARGET URL")
        tk.Label(sb, text="Paste your URL below:",
                 font=("Helvetica", 8), fg=C["grey"],
                 bg=C["panel"], anchor="w").pack(fill="x", padx=14, pady=(0, 3))

        self.url_entry = tk.Entry(sb, textvariable=self.url_var,
            font=("Courier", 9),
            bg=C["input"], fg=C["white"],
            insertbackground=C["red"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["red"])
        self.url_entry.pack(fill="x", padx=10, ipady=5, pady=(0, 4))

        tk.Button(sb, text="Clear URL",
            font=("Helvetica", 8), bg=C["bg"],
            fg=C["grey"], relief="flat", cursor="hand2",
            pady=3, bd=0, highlightthickness=0,
            command=lambda: self.url_var.set("")
        ).pack(fill="x", padx=10, pady=(0, 4))

        # ── Pages ──
        sec("PAGES TO SCRAPE")

        pg_row = tk.Frame(sb, bg=C["panel"])
        pg_row.pack(fill="x", padx=10, pady=(0, 4))

        self.pages_entry = tk.Entry(pg_row, textvariable=self.pages_var,
            font=("Courier", 10), width=5,
            bg=C["input"], fg=C["white"],
            insertbackground=C["red"],
            justify="center", relief="flat",
            highlightthickness=1,
            highlightbackground=C["border"],
            highlightcolor=C["red"])
        self.pages_entry.pack(side="left", ipady=5, padx=(0, 8))

        tk.Label(pg_row, text="pages (any number)",
                 font=("Helvetica", 8), fg=C["grey"],
                 bg=C["panel"]).pack(side="left")

        quick = tk.Frame(sb, bg=C["panel"])
        quick.pack(fill="x", padx=10, pady=(0, 4))
        for n in [1, 2, 3, 5, 10]:
            tk.Button(quick, text=str(n),
                font=("Helvetica", 9, "bold"),
                bg=C["bg"], fg=C["grey"],
                relief="flat", cursor="hand2",
                width=3, pady=3,
                bd=0, highlightthickness=0,
                command=lambda v=n: self.pages_var.set(str(v))
            ).pack(side="left", padx=2)

        # ── Actions ──
        sec("ACTIONS")
        actions = [
            ("Scrape Data",  self._start_scrape, C["red"],   C["white"]),
            ("Save JSON",    self._save_json,     C["input"], C["grey"]),
            ("Save CSV",     self._save_csv,      C["input"], C["grey"]),
            ("Export Excel", self._save_excel,    C["input"], C["grey"]),
            ("Clear Data",   self._clear_data,    C["bg"],    C["grey"]),
        ]
        for lbl, cmd, bg, fg in actions:
            b = tk.Button(sb, text=lbl, command=cmd,
                font=("Helvetica", 10, "bold"),
                fg=fg, bg=bg, relief="flat",
                cursor="hand2", pady=8,
                anchor="w", padx=14,
                activebackground=C["red_hover"],
                activeforeground=C["white"],
                bd=0, highlightthickness=0)
            b.pack(fill="x", padx=10, pady=2)
            _bg, _fg = bg, fg
            b.bind("<Enter>", lambda e, w=b: w.config(bg=C["red_dark"], fg=C["white"]))
            b.bind("<Leave>", lambda e, w=b, bk=_bg, fc=_fg: w.config(bg=bk, fg=fc))

        # ── Stats ──
        sec("STATISTICS")
        self.stat_vars = {}
        for key, default in [("Total", "0"), ("Displayed", "0"), ("Category", "-")]:
            row = tk.Frame(sb, bg=C["panel"])
            row.pack(fill="x", padx=14, pady=2)
            tk.Label(row, text=key,
                     font=("Helvetica", 9), fg=C["grey"],
                     bg=C["panel"], anchor="w", width=10).pack(side="left")
            var = tk.StringVar(value=default)
            tk.Label(row, textvariable=var,
                     font=("Helvetica", 9, "bold"),
                     fg=C["red"], bg=C["panel"],
                     anchor="e").pack(side="right")
            self.stat_vars[key] = var

        tk.Frame(sb, bg=C["border"], height=1).pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(sb, text="PROGRESS",
                 font=("Helvetica", 8, "bold"),
                 fg=C["grey_d"], bg=C["panel"]).pack(padx=14, anchor="w")
        self.progress = ttk.Progressbar(sb, mode="indeterminate", length=190)
        self.progress.pack(padx=10, pady=(4, 12), fill="x")

    def _select_cat(self, cat):
        self.category_var.set(cat)
        for c, b in self._cat_btns.items():
            if c == cat:
                b.config(bg=C["red_dark"], fg=C["white"])
            else:
                b.config(bg=C["input"], fg=C["grey"])

    # ── Main Area ─────────────────────────────
    def _build_main_area(self, parent):
        main = tk.Frame(parent, bg=C["bg"])
        main.pack(side="right", fill="both", expand=True)
        self._build_toolbar(main)
        self._build_table(main)
        self._build_log(main)

    def _build_toolbar(self, parent):
        tb = tk.Frame(parent, bg=C["panel"],
                      highlightbackground=C["border"], highlightthickness=1)
        tb.pack(fill="x", pady=(0, 8))

        tk.Label(tb, text="Search:",
                 font=("Helvetica", 9, "bold"),
                 fg=C["grey"], bg=C["panel"]).pack(side="left", padx=(12, 6), pady=8)

        self.search_entry = tk.Entry(tb, textvariable=self.search_var,
            font=("Helvetica", 10),
            bg=C["input"], fg=C["text"],
            insertbackground=C["red"],
            relief="flat",
            highlightthickness=1,
            highlightcolor=C["red"],
            highlightbackground=C["border"])
        self.search_entry.pack(side="left", fill="x", expand=True,
                               pady=8, padx=4, ipady=4)
        self.search_var.trace_add("write", lambda *_: self._filter())

        tk.Label(tb, text="|", fg=C["border"],
                 bg=C["panel"]).pack(side="left", padx=6)

        for lbl, key in [("Sort Title", "Title"), ("Sort Date", "Date"), ("Sort Source", "Source")]:
            b = tk.Button(tb, text=lbl,
                font=("Helvetica", 9), bg=C["bg"],
                fg=C["grey"], relief="flat",
                cursor="hand2", padx=10, pady=5,
                bd=0, highlightthickness=0,
                command=lambda k=key: self._sort(k))
            b.pack(side="left", padx=3, pady=8)
            b.bind("<Enter>", lambda e, w=b: w.config(fg=C["white"]))
            b.bind("<Leave>", lambda e, w=b: w.config(fg=C["grey"]))

        self.count_lbl = tk.Label(tb, text="0 records",
            font=("Helvetica", 9, "bold"),
            fg=C["grey"], bg=C["panel"])
        self.count_lbl.pack(side="right", padx=14)

    def _build_table(self, parent):
        frame = tk.Frame(parent, bg=C["bg"])
        frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(frame, selectmode="extended", show="headings")

        vsb = ttk.Scrollbar(frame, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        self.tree.tag_configure("even", background=C["card"])
        self.tree.tag_configure("odd",  background="#0F0F0F")

        self.tree.bind("<Double-1>", self._open_link)
        self.tree.bind("<Button-3>", self._context_menu)

        self._ctx = tk.Menu(self, tearoff=0,
                            bg=C["panel"], fg=C["text"],
                            activebackground=C["red_dark"],
                            activeforeground=C["white"],
                            font=("Helvetica", 9))
        self._ctx.add_command(label="Open Link",      command=self._open_selected)
        self._ctx.add_command(label="Copy Row",       command=self._copy_row)
        self._ctx.add_separator()
        self._ctx.add_command(label="Delete Row",     command=self._delete_rows)

    def _build_log(self, parent):
        lf = tk.Frame(parent, bg=C["bg"])
        lf.pack(fill="x", pady=(8, 0))

        hdr = tk.Frame(lf, bg=C["panel"],
                       highlightbackground=C["border"], highlightthickness=1)
        hdr.pack(fill="x")

        tk.Label(hdr, text="ACTIVITY LOG",
                 font=("Helvetica", 8, "bold"),
                 fg=C["red"], bg=C["panel"]).pack(side="left", padx=14, pady=5)

        tk.Button(hdr, text="Clear",
            font=("Helvetica", 8), bg=C["bg"],
            fg=C["grey"], relief="flat",
            cursor="hand2", padx=8, pady=3,
            bd=0, highlightthickness=0,
            command=self._clear_log
        ).pack(side="right", padx=10, pady=5)

        self.log_text = tk.Text(lf, height=7,
            bg=C["card"], fg=C["text_dim"],
            font=("Courier", 9), relief="flat",
            state="disabled", wrap="word",
            padx=12, pady=8,
            selectbackground=C["red_dark"])
        self.log_text.pack(fill="x")

        self.log_text.tag_config("info",    foreground=C["text_dim"])
        self.log_text.tag_config("success", foreground=C["green"])
        self.log_text.tag_config("error",   foreground=C["error"])
        self.log_text.tag_config("warning", foreground=C["yellow"])

    def _build_statusbar(self):
        sb = tk.Frame(self, bg=C["panel"], height=24,
                      highlightbackground=C["red_dark"], highlightthickness=1)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)

        tk.Label(sb, textvariable=self.status_var,
                 font=("Helvetica", 9), fg=C["grey"],
                 bg=C["panel"]).pack(side="left", padx=14)

        tk.Label(sb, text="Dynamic Web Scraper PRO  |  Python + Tkinter",
                 font=("Helvetica", 8), fg=C["grey_d"],
                 bg=C["panel"]).pack(side="right", padx=14)

    # ── Helpers ───────────────────────────────
    def _log(self, msg, kind="info"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"[{ts}]  {msg}\n", kind)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _log_safe(self, msg, kind="info"):
        self.after(0, self._log, msg, kind)

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _tick_clock(self):
        self.clock_lbl.config(
            text=datetime.datetime.now().strftime("%a  %d %b %Y  %H:%M:%S"))
        self.after(1000, self._tick_clock)

    def _update_stats(self):
        self.stat_vars["Total"].set(str(len(self.data)))
        self.stat_vars["Displayed"].set(str(len(self.filtered_data)))
        self.stat_vars["Category"].set(self.category_var.get())
        self.count_lbl.config(text=f"{len(self.filtered_data)} records")

    def _get_pages(self):
        try:
            return max(1, int(self.pages_var.get()))
        except ValueError:
            return 2

    # ── Table ─────────────────────────────────
    def _setup_columns(self):
        cat  = self.category_var.get()
        cols = self.COLUMNS[cat]
        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=c.upper(),
                              command=lambda _c=c: self._sort(_c))
            self.tree.column(c, width=self.COL_W.get(c, 140),
                             minwidth=50, anchor="w")

    def _populate(self):
        self.tree.delete(*self.tree.get_children())
        cols = self.COLUMNS[self.category_var.get()]
        for i, row in enumerate(self.filtered_data):
            vals = [str(row.get(c, "N/A")) for c in cols]
            self.tree.insert("", "end", values=vals,
                             tags=("even" if i % 2 == 0 else "odd",))

    def _filter(self):
        kw = self.search_var.get().strip().lower()
        self.filtered_data = [
            r for r in self.data
            if not kw or any(kw in str(v).lower() for v in r.values())
        ]
        self._populate()
        self._update_stats()

    def _sort(self, key):
        self._sort_rev = not self._sort_rev if self._sort_col == key else False
        self._sort_col = key
        self.filtered_data.sort(
            key=lambda x: str(x.get(key, "")).lower(),
            reverse=self._sort_rev)
        self._populate()

    # ── Scraping ──────────────────────────────
    def _start_scrape(self):
        if self.scraping:
            messagebox.showinfo("Busy", "Scraping already in progress.")
            return
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("No URL",
                "Please enter a URL in the Target URL field.")
            return
        if not url.startswith("http"):
            messagebox.showwarning("Invalid URL",
                "URL must start with http:// or https://")
            return

        self.scraping = True
        self.data.clear()
        self.filtered_data.clear()
        self.progress.start(10)
        self.status_var.set("Scraping...")
        cat   = self.category_var.get()
        pages = self._get_pages()
        self._setup_columns()
        self._log(f"Started  |  {cat}  |  Pages: {pages}  |  {url}", "info")

        threading.Thread(
            target=self._run_scrape,
            args=(cat, url, pages),
            daemon=True
        ).start()

    def _run_scrape(self, cat, url, pages):
        try:
            if cat == "Jobs":
                self.data = scrape_jobs(url, pages, self._log_safe)
            elif cat == "Products":
                self.data = scrape_products(url, pages, self._log_safe)
            elif cat == "News":
                self.data = scrape_news(url, pages, self._log_safe)
        except Exception as e:
            self.after(0, self._log, f"Fatal: {e}", "error")
        finally:
            self.after(0, self._scrape_done)

    def _scrape_done(self):
        self.scraping = False
        self.progress.stop()
        self.filtered_data = list(self.data)
        self._populate()
        self._update_stats()
        n = len(self.data)
        self.status_var.set(f"Done  |  {n} records  |  {self.category_var.get()}")
        self._log(f"Complete. {n} records loaded. Double-click a row to open its link.", "success")

    # ── Save ──────────────────────────────────
    def _has_data(self):
        if not self.data:
            messagebox.showwarning("No Data", "Please scrape data first.")
            return False
        return True

    def _save_json(self):
        if not self._has_data(): return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON File", "*.json")],
            initialfile=f"scraped_{self.category_var.get().lower()}_{timestamp()}.json")
        if not path: return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        self._log(f"Saved JSON: {path}", "success")
        self.status_var.set(f"Saved: {os.path.basename(path)}")

    def _save_csv(self):
        if not self._has_data(): return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV File", "*.csv")],
            initialfile=f"scraped_{self.category_var.get().lower()}_{timestamp()}.csv")
        if not path: return
        keys = list(self.data[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(self.data)
        self._log(f"Saved CSV: {path}", "success")
        self.status_var.set(f"Saved: {os.path.basename(path)}")

    def _save_excel(self):
        if not self._has_data(): return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel File", "*.xlsx")],
            initialfile=f"scraped_{self.category_var.get().lower()}_{timestamp()}.xlsx")
        if not path: return
        try:
            pd.DataFrame(self.data).to_excel(path, index=False)
            self._log(f"Saved Excel: {path}", "success")
            self.status_var.set(f"Saved: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Excel Error", str(e))

    def _clear_data(self):
        if messagebox.askyesno("Clear", "Clear all scraped data?"):
            self.data.clear()
            self.filtered_data.clear()
            self.tree.delete(*self.tree.get_children())
            self._update_stats()
            self._log("Data cleared.", "warning")
            self.status_var.set("Cleared.")

    # ── Table Actions ─────────────────────────
    def _link_column(self):
        return {"Jobs": "Apply Link",
                "Products": "Product Link",
                "News": "Link"}.get(self.category_var.get(), "Link")

    def _open_link(self, event=None):
        item = self.tree.focus()
        if not item: return
        values = self.tree.item(item, "values")
        cols   = self.COLUMNS[self.category_var.get()]
        lc     = self._link_column()
        if lc in cols:
            idx  = cols.index(lc)
            link = values[idx] if idx < len(values) else ""
            if link and link.startswith("http"):
                import webbrowser
                webbrowser.open(link)
                self._log(f"Opened: {link}", "info")

    def _open_selected(self):
        self._open_link()

    def _copy_row(self):
        item = self.tree.focus()
        if not item: return
        values = self.tree.item(item, "values")
        self.clipboard_clear()
        self.clipboard_append("\t".join(str(v) for v in values))
        self._log("Row copied to clipboard.", "info")

    def _delete_rows(self):
        sel = self.tree.selection()
        for item in sel:
            self.tree.delete(item)
        self._log(f"Deleted {len(sel)} row(s) from view.", "warning")

    def _context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self._ctx.tk_popup(event.x_root, event.y_root)


# ──────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()