"""
news_fetcher.py – Multi-source news aggregator for SET stocks
--------------------------------------------------------------
Aggregates news from: yfinance, SET, Thunhoon, GapFocus, Google News.
Returns deduplicated, date-filtered list sorted newest-first.
"""
import logging
import re
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def get_all_news(symbol: str, days_back: int = 15) -> list:
    """
    Aggregate news from all available sources.
    Returns list of dicts sorted newest-first, filtered to last `days_back` days.
    """
    symbol_clean = symbol.upper().removesuffix(".BK")
    cutoff = datetime.now() - timedelta(days=days_back)
    all_articles = []

    # ── Source 1: yfinance (fastest, no browser needed) ──────────────
    try:
        yf_news = _fetch_yfinance_news(symbol_clean)
        all_articles.extend(yf_news)
        logger.info(f"yfinance: {len(yf_news)} articles for {symbol_clean}")
    except Exception as e:
        logger.warning(f"yfinance news failed: {e}")

    # ── Source 2: Google News (requests-based) ───────────────────────
    try:
        gn_news = _fetch_google_news(symbol_clean)
        all_articles.extend(gn_news)
        logger.info(f"Google News: {len(gn_news)} articles for {symbol_clean}")
    except Exception as e:
        logger.warning(f"Google News failed: {e}")

    # ── Source 3: GapFocus (requests + BS4) ──────────────────────────
    try:
        gf_news = _fetch_gapfocus_news(symbol_clean)
        all_articles.extend(gf_news)
        logger.info(f"GapFocus: {len(gf_news)} articles for {symbol_clean}")
    except Exception as e:
        logger.warning(f"GapFocus news failed: {e}")

    # ── Source 4: SET news (Selenium - Skip on Render for speed) ──────
    if not os.environ.get("RENDER"):
        try:
            set_news = _fetch_set_news(symbol_clean)
            all_articles.extend(set_news)
            logger.info(f"SET: {len(set_news)} articles for {symbol_clean}")
        except Exception as e:
            logger.warning(f"SET news failed: {e}")
    else:
        logger.info("Skipping SET news Selenium scrape on Render.")

    # ── Source 5: Thunhoon (Selenium - Skip on Render for speed) ─────
    if not os.environ.get("RENDER"):
        try:
            th_news = _fetch_thunhoon_news(symbol_clean)
            all_articles.extend(th_news)
            logger.info(f"Thunhoon: {len(th_news)} articles for {symbol_clean}")
        except Exception as e:
            logger.warning(f"Thunhoon news failed: {e}")
    else:
        logger.info("Skipping Thunhoon news Selenium scrape on Render.")
    # ── Source 6: RYT9 (requests + BS4) ──────────────────────────────
    try:
        ryt9_news = _fetch_ryt9_news(symbol_clean)
        all_articles.extend(ryt9_news)
        logger.info(f"RYT9: {len(ryt9_news)} articles for {symbol_clean}")
    except Exception as e:
        logger.warning(f"RYT9 news failed: {e}")
    # ── Filter by date ───────────────────────────────────────────────
    filtered = []
    for art in all_articles:
        try:
            d = art.get("date")
            if d:
                dt = datetime.strptime(d, "%Y-%m-%d")
                if dt >= cutoff:
                    filtered.append(art)
            else:
                filtered.append(art)  # Keep if no date (show at end)
        except Exception:
            filtered.append(art)

    # ── Deduplicate by title similarity ──────────────────────────────
    seen_titles = set()
    unique = []
    for art in filtered:
        norm = _normalize_title(art.get("title", ""))
        if norm and norm not in seen_titles:
            seen_titles.add(norm)
            unique.append(art)

    # ── Sort by date (newest first) ──────────────────────────────────
    def _sort_key(a):
        try:
            return datetime.strptime(a.get("date", "1970-01-01"), "%Y-%m-%d")
        except Exception:
            return datetime(1970, 1, 1)

    unique.sort(key=_sort_key, reverse=True)
    return unique


# ---------------------------------------------------------------------------
# Source: yfinance
# ---------------------------------------------------------------------------
def _fetch_yfinance_news(symbol: str) -> list:
    import yfinance as yf
    try:
        from data_fetcher import get_yf_session
        session = get_yf_session()
    except Exception:
        session = None

    articles = []
    for ticker_str in [f"{symbol}.BK", symbol]:
        try:
            t = yf.Ticker(ticker_str, session=session) if session else yf.Ticker(ticker_str)
            news_list = t.news or []
            for item in news_list:
                # yfinance news format varies by version
                title = item.get("title") or item.get("headline") or ""
                link = item.get("link") or item.get("url") or ""
                publisher = item.get("publisher") or item.get("source") or "Yahoo Finance"
                ts = item.get("providerPublishTime") or item.get("publish_time")

                date_str = ""
                if ts:
                    try:
                        date_str = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
                    except Exception:
                        date_str = ""

                if title:
                    articles.append({
                        "title": title,
                        "url": link,
                        "source": "Yahoo Finance",
                        "source_icon": "📰",
                        "date": date_str,
                        "snippet": title[:200],
                    })
            if articles:
                break
        except Exception:
            continue
    return articles


# ---------------------------------------------------------------------------
# Source: Google News (via RSS)
# ---------------------------------------------------------------------------
def _fetch_google_news(symbol: str) -> list:
    import requests
    from bs4 import BeautifulSoup

    articles = []
    query = f"{symbol} SET Thailand stock"
    url = f"https://news.google.com/rss/search?q={query}&hl=en&gl=TH&ceid=TH:en"

    try:
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "xml")
            items = soup.find_all("item", limit=20)
            for item in items:
                title = item.find("title")
                link = item.find("link")
                pub_date = item.find("pubDate")
                source = item.find("source")

                date_str = ""
                if pub_date and pub_date.text:
                    try:
                        dt = datetime.strptime(
                            pub_date.text.strip(),
                            "%a, %d %b %Y %H:%M:%S %Z"
                        )
                        date_str = dt.strftime("%Y-%m-%d")
                    except Exception:
                        try:
                            # Try alternate format
                            dt = datetime.strptime(
                                pub_date.text.strip()[:25],
                                "%a, %d %b %Y %H:%M:%S"
                            )
                            date_str = dt.strftime("%Y-%m-%d")
                        except Exception:
                            pass

                if title and title.text:
                    articles.append({
                        "title": title.text.strip(),
                        "url": link.text.strip() if link else "",
                        "source": f"Google News ({source.text.strip() if source else 'Web'})",
                        "source_icon": "🌐",
                        "date": date_str,
                        "snippet": title.text.strip()[:200],
                    })
    except Exception as e:
        logger.debug(f"Google News RSS error: {e}")

    return articles


# ---------------------------------------------------------------------------
# Source: GapFocus
# ---------------------------------------------------------------------------
def _fetch_gapfocus_news(symbol: str) -> list:
    import requests
    from bs4 import BeautifulSoup

    articles = []
    url = f"https://www.gapfocus.com/stock/{symbol}"

    try:
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")

            # Try to find news/discussion items
            for a_tag in soup.find_all("a", href=True, limit=30):
                text = a_tag.get_text(strip=True)
                href = a_tag["href"]
                # Filter: only meaningful links (not nav)
                if (len(text) > 20 and
                    symbol.lower() in text.lower() and
                    not href.startswith("#") and
                    "gapfocus" in href or href.startswith("http")):

                    if not href.startswith("http"):
                        href = f"https://www.gapfocus.com{href}"

                    articles.append({
                        "title": text[:200],
                        "url": href,
                        "source": "GapFocus",
                        "source_icon": "📊",
                        "date": _extract_date_from_text(text) or datetime.now().strftime("%Y-%m-%d"),
                        "snippet": text[:200],
                    })
    except Exception as e:
        logger.debug(f"GapFocus error: {e}")

    return articles[:15]


# ---------------------------------------------------------------------------
# Source: RYT9
# ---------------------------------------------------------------------------
def _fetch_ryt9_news(symbol: str) -> list:
    import requests
    from bs4 import BeautifulSoup

    articles = []
    url = f"https://www.ryt9.com/search?q={symbol}"

    try:
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "html.parser")
            # Select each list item
            for item in soup.select(".list-block"):
                title_tag = item.select_one("a.list-title")
                if title_tag:
                    title = title_tag.get_text(strip=True)
                    href = title_tag["href"]
                    if not href.startswith("http"):
                        href = f"https://www.ryt9.com{href}"

                    # Date is usually in the first span of the <p>
                    date_span = item.select_one("p span:first-child")
                    date_str = ""
                    if date_span:
                        date_str = _extract_date_from_text(date_span.get_text())

                    articles.append({
                        "title": title,
                        "url": href,
                        "source": "RYT9",
                        "source_icon": "📑",
                        "date": date_str,
                        "snippet": title,
                    })
    except Exception as e:
        logger.debug(f"RYT9 error: {e}")

    return articles[:15]


# ---------------------------------------------------------------------------
# Source: SET (Selenium – JS rendered)
# ---------------------------------------------------------------------------
def _fetch_set_news(symbol: str) -> list:
    articles = []
    try:
        driver = _get_headless_driver()
        if not driver:
            return []

        url = f"https://www.set.or.th/en/market/product/stock/quote/{symbol}/news"
        driver.get(url)

        import time
        time.sleep(4)  # Wait for JS rendering

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(driver.page_source, "html.parser")
        driver.quit()

        # SET news items are typically in a list/table structure
        # Look for common patterns
        for a_tag in soup.find_all("a", href=True):
            text = a_tag.get_text(strip=True)
            href = a_tag["href"]
            if len(text) > 15 and "/news" not in href.split("?")[0].rsplit("/", 1)[-1]:
                # Skip navigation links
                if any(kw in href.lower() for kw in ["news", "announcement", "disclosure"]):
                    if not href.startswith("http"):
                        href = f"https://www.set.or.th{href}"
                    articles.append({
                        "title": text[:200],
                        "url": href,
                        "source": "SET",
                        "source_icon": "🏦",
                        "date": _extract_date_from_text(text),
                        "snippet": text[:200],
                    })

    except Exception as e:
        logger.warning(f"SET Selenium error: {e}")

    return articles[:15]


# ---------------------------------------------------------------------------
# Source: Thunhoon (Selenium – JS rendered)
# ---------------------------------------------------------------------------
def _fetch_thunhoon_news(symbol: str) -> list:
    articles = []
    try:
        driver = _get_headless_driver()
        if not driver:
            return []

        url = f"https://thunhoon.com/search?q={symbol}"
        driver.get(url)

        import time
        time.sleep(4)

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(driver.page_source, "html.parser")
        driver.quit()

        # Thunhoon search results – look for article links
        for a_tag in soup.find_all("a", href=True):
            text = a_tag.get_text(strip=True)
            href = a_tag["href"]
            if (len(text) > 20 and
                symbol.lower() in text.lower() and
                not href.endswith("/search") and
                "category" not in href):

                if not href.startswith("http"):
                    href = f"https://thunhoon.com{href}"

                articles.append({
                    "title": text[:200],
                    "url": href,
                    "source": "Thunhoon",
                    "source_icon": "📈",
                    "date": _extract_date_from_text(text),
                    "snippet": text[:200],
                })

    except Exception as e:
        logger.warning(f"Thunhoon Selenium error: {e}")

    return articles[:15]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_headless_driver():
    """Create a headless Chrome/Edge Selenium driver."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options as ChromeOptions

        opts = ChromeOptions()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1280,720")
        opts.add_argument("--log-level=3")
        opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        driver = webdriver.Chrome(options=opts)
        driver.set_page_load_timeout(15)
        return driver
    except Exception:
        try:
            from selenium import webdriver
            from selenium.webdriver.edge.options import Options as EdgeOptions

            opts = EdgeOptions()
            opts.add_argument("--headless=new")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--window-size=1280,720")
            driver = webdriver.Edge(options=opts)
            driver.set_page_load_timeout(15)
            return driver
        except Exception as e:
            logger.warning(f"No Selenium driver available: {e}")
            return None


def _normalize_title(title: str) -> str:
    """Normalize title for deduplication."""
    return re.sub(r"[^a-z0-9]", "", title.lower())[:60]


def _extract_date_from_text(text: str) -> str:
    """Try to extract a date from text, return ISO format or today."""
    # Common patterns: "28 Apr 2026", "2026-04-28", "Apr 28, 2026"
    patterns = [
        (r"(\d{4}-\d{2}-\d{2})", "%Y-%m-%d"),
        (r"(\d{1,2}\s+\w{3}\s+\d{4})", "%d %b %Y"),
        (r"(\w{3}\s+\d{1,2},?\s+\d{4})", "%b %d, %Y"),
    ]
    for pat, fmt in patterns:
        m = re.search(pat, text)
        if m:
            try:
                return datetime.strptime(m.group(1).replace(",", ""), fmt).strftime("%Y-%m-%d")
            except Exception:
                pass
    return ""
