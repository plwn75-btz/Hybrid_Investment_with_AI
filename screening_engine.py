"""
SET Stock Screening Engine
Reusable module extracted from SET_Screening.py for use by the web dashboard.
"""

import pandas as pd
import yfinance as yf
from datetime import date, datetime, timedelta
import numpy as np
import os
import sys
import time
import calendar
import logging
import gc
from ta.trend import PSARIndicator, MACD
from ta.momentum import StochasticOscillator, RSIIndicator
from ta.volatility import BollingerBands
import certifi
import warnings
import traceback

logger = logging.getLogger(__name__)

warnings.simplefilter(action='ignore', category=FutureWarning)

# --- SSL FIX ---
os.environ['SSL_CERT_FILE'] = certifi.where()

# --- YFINANCE CACHE FIX ---
if os.environ.get("RENDER"):
    # On Render/Linux, use /tmp which is guaranteed to be writable
    cache_dir = "/tmp/py_cache"
else:
    # On Local/Windows, use current directory
    cache_dir = os.path.join(os.getcwd(), "py_cache")

try:
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
    yf.set_tz_cache_location(cache_dir)
except Exception as e:
    print(f"Warning: Could not set yfinance cache at {cache_dir}: {e}")


def is_workday(date_obj):
    """Check if a date is a workday (Monday=0 to Friday=4)."""
    return date_obj.weekday() < 5


def adjust_to_last_friday(date_obj):
    """Adjust date to the last Friday if it falls on a weekend."""
    while date_obj.weekday() > 4:
        date_obj -= timedelta(days=1)
    return date_obj


def get_default_date():
    """Calculate the default screening date (yesterday or end of last month)."""
    today = date.today()
    if today.day == 1:
        month, year = (today.month - 1, today.year) if today.month > 1 else (12, today.year - 1)
        return date(year, month, calendar.monthrange(year, month)[1])
    return today - timedelta(days=1)


def resolve_date(date_str):
    """Parse date string and adjust for weekends. Returns (resolved_date_str, message)."""
    try:
        input_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        input_date = date.today() - timedelta(days=1)
        return str(input_date), f"Invalid date format. Using {input_date}."

    if is_workday(input_date):
        return str(input_date), f"{input_date.strftime('%Y-%m-%d')} is a workday."
    else:
        adjusted = adjust_to_last_friday(input_date)
        return str(adjusted), f"{input_date.strftime('%Y-%m-%d')} is a weekend. Adjusted to {adjusted.strftime('%Y-%m-%d')}."


def calculate_rsi(data, period=14):
    """Calculate RSI indicator using Wilder's Smoothing."""
    try:
        rsi_ind = RSIIndicator(close=data['Close'], window=period)
        return rsi_ind.rsi()
    except Exception:
        return np.nan


def calculate_psar(data):
    """Calculate Parabolic SAR using the ta library."""
    psar_indicator = PSARIndicator(
        high=data['High'],
        low=data['Low'],
        close=data['Close'],
        step=0.02,
        max_step=0.2
    )
    return psar_indicator.psar()


def calculate_indicators(data):
    """Calculate all technical indicators for a stock."""
    try:
        # MACD
        macd_ind = MACD(close=data['Close'], window_slow=26, window_fast=12, window_sign=9)
        data['MACD'] = macd_ind.macd()
    except Exception:
        data['MACD'] = np.nan

    try:
        # Stochastic Oscillator
        stoch_ind = StochasticOscillator(high=data['High'], low=data['Low'], close=data['Close'], window=14, smooth_window=3)
        data['STOCHk'] = stoch_ind.stoch()
    except Exception:
        data['STOCHk'] = np.nan

    # Parabolic SAR
    try:
        data['SAR'] = calculate_psar(data)
    except Exception:
        data['SAR'] = np.nan

    try:
        # Bollinger Bands
        bb_ind = BollingerBands(close=data['Close'], window=20, window_dev=2)
        data['BBL'] = bb_ind.bollinger_lband()
        data['BBM'] = bb_ind.bollinger_mavg()
        data['BBU'] = bb_ind.bollinger_hband()
    except Exception:
        data['BBL'] = np.nan
        data['BBM'] = np.nan
        data['BBU'] = np.nan

    return data


def check_conditions_on_data(symbol, data, date_str, set_rsi, set_stoch, error_tracker):
    """
    Check screening conditions for a single stock using provided DataFrame.
    This is called by the batch downloader.
    """
    try:
        if data is None or data.empty:
            error_tracker['no_data'].append(symbol)
            return None

        if len(data) < 200:
            error_tracker['insufficient_data'].append(symbol)
            return None

        # Calculate EMA50, EMA200, RSI
        data = data.copy() # Avoid SettingWithCopyWarning
        data['EMA50'] = data['Close'].ewm(span=50, adjust=False).mean()
        data['EMA200'] = data['Close'].ewm(span=200, adjust=False).mean()
        data['RSI'] = calculate_rsi(data)

        # Calculate all other indicators
        data = calculate_indicators(data)

        # Find latest available date on or before requested date
        idx_strs = data.index.strftime('%Y-%m-%d')
        valid_mask = idx_strs <= date_str

        if not valid_mask.any():
            error_tracker['missing_date'].append(symbol)
            return None

        row = data.loc[valid_mask].iloc[-1]
        
        # Calculate 5-Day Average Volume based on the valid dates
        valid_data = data.loc[valid_mask]
        volume_5d_avg = valid_data['Volume'].tail(5).mean() if not valid_data.empty else np.nan

        try:
            close_price = row['Close']
            volume = row['Volume']
            ema50 = row['EMA50']
            ema200 = row['EMA200']
            rsi = row['RSI']
            macd = row['MACD']
            stochk = row['STOCHk']
            sar = row['SAR']
            bbl = row['BBL']
            bbm = row['BBM']
            bbu = row['BBU']

            # Validate all critical values are not None/NaN
            critical_values = [close_price, volume, volume_5d_avg, ema50, ema200, rsi, macd, stochk, sar, bbl, bbm, bbu]
            if any(pd.isna(val) for val in critical_values):
                error_tracker['nan_values'].append(symbol)
                return None

            close_price = round(close_price, 2)
            volume = int(volume) if not pd.isna(volume) else 0
            volume_5d_avg = int(volume_5d_avg) if not pd.isna(volume_5d_avg) else 0
            ema50 = round(ema50, 4)
            ema200 = round(ema200, 4)
            rsi = round(rsi, 4)
            macd = round(macd, 4)
            stochk = round(stochk, 4)
            sar = round(sar, 4)
            bbl = round(bbl, 4)
            bbm = round(bbm, 4)
            bbu = round(bbu, 4)

        except (KeyError, TypeError, IndexError):
            error_tracker['calculation_error'].append(symbol)
            return None

        # 6 criteria
        criteria_1 = bool(close_price > ema200 and ema50 > ema200)
        criteria_2 = bool(rsi < int(set_rsi))
        criteria_3 = bool(macd > 0)
        criteria_4 = bool(stochk > int(set_stoch))
        criteria_5 = bool(close_price < bbm and close_price > bbl)
        criteria_6 = bool(close_price > sar)

        criteria_list = [criteria_1, criteria_2, criteria_3, criteria_4, criteria_5, criteria_6]
        total_passed = sum(criteria_list)

        return {
            'date': date_str,
            'symbol': symbol.replace('.BK', ''),
            'criteria_passed': total_passed,
            'close': close_price,
            'volume': volume,
            'volume_5d_avg': volume_5d_avg,
            'ema50': ema50,
            'ema200': ema200,
            'rsi': rsi,
            'macd': macd,
            'stoch': stochk,
            'sar': sar,
            'bbl': bbl,
            'bbm': bbm,
            'bbu': bbu,
            'c1': criteria_1,
            'c2': criteria_2,
            'c3': criteria_3,
            'c4': criteria_4,
            'c5': criteria_5,
            'c6': criteria_6,
        }

    except Exception:
        error_tracker['calculation_error'].append(symbol)
        return None


def load_stock_list():
    """Load the SET stock list CSV."""
    if getattr(sys, 'frozen', False):
        # Bundled in EXE (read-only assets)
        script_dir = sys._MEIPASS
    else:
        # Running normally
        script_dir = os.path.dirname(os.path.abspath(__file__))

    csv_path = os.path.join(script_dir, "set_stock_list_with_bk.csv")
    df = pd.read_csv(csv_path)

    if 'Symbol' not in df.columns:
        raise ValueError("The 'Symbol' column is missing from the CSV file.")

    df['Symbol'] = df['Symbol'].apply(lambda x: f"{x}.BK" if not x.endswith(".BK") else x)
    return df['Symbol'].tolist()


def run_screening(date_str, rsi_threshold=30, stoch_threshold=70, progress_callback=None):
    """
    Run the full stock screening.
    
    Args:
        date_str: Date in YYYY-MM-DD format
        rsi_threshold: RSI oversold threshold (default 30)
        stoch_threshold: Stochastic threshold (default 70)
        progress_callback: Optional callable(current, total) for progress updates
    
    Returns:
        dict with keys 'results' (grouped by criteria count), 'summary', 'errors'
    """
    # Resolve date
    resolved_date, date_message = resolve_date(date_str)

    # Load stocks
    stock_symbols = load_stock_list()
    total = len(stock_symbols)

    error_tracker = {
        'delisted': [],
        'no_data': [],
        'insufficient_data': [],
        'missing_date': [],
        'nan_values': [],
        'calculation_error': []
    }

    # Group results by criteria count (0-6)
    results = {i: [] for i in range(7)}

    # Batch process stocks (10 at a time) for memory safety on Render Free tier
    batch_size = 10
    for i in range(0, total, batch_size):
        batch = stock_symbols[i : i + batch_size]
        try:
            try:
                from data_fetcher import get_yf_session
                session = get_yf_session()
            except Exception:
                session = None

            # Download batch data
            # threads=False is much more memory efficient
            if session:
                data = yf.download(batch, period='1y', group_by='ticker', threads=False, progress=False, session=session)
            else:
                data = yf.download(batch, period='1y', group_by='ticker', threads=False, progress=False)
            
            for symbol_idx, symbol in enumerate(batch):
                try:
                    # Extract single stock data
                    if len(batch) > 1:
                        # Use .copy() to ensure we don't keep references to the whole batch
                        symbol_data = data[symbol].dropna(how='all').copy()
                    else:
                        symbol_data = data.dropna(how='all').copy()

                    result = check_conditions_on_data(symbol, symbol_data, resolved_date, rsi_threshold, stoch_threshold, error_tracker)
                    if result:
                        results[result['criteria_passed']].append(result)
                    
                    # Clean up symbol_data immediately
                    del symbol_data
                except Exception:
                    error_tracker['calculation_error'].append(symbol)
                
                if progress_callback:
                    progress_callback(i + symbol_idx + 1, total)
            
            # Clean up the large batch dataframe
            del data
            gc.collect() # Force memory release
            
        except Exception as e:
            logger.error(f"Batch download failed: {e}")
            for s in batch:
                error_tracker['no_data'].append(s)
            if progress_callback:
                progress_callback(min(i + batch_size, total), total)
        
        # Small sleep between batches to avoid YFRateLimitError
        time.sleep(1.5)

    # Build summary
    total_processed = sum(len(v) for v in results.values())
    total_skipped = sum(len(v) for v in error_tracker.values())

    summary = {
        'date': resolved_date,
        'date_message': date_message,
        'rsi_threshold': rsi_threshold,
        'stoch_threshold': stoch_threshold,
        'total_stocks': total,
        'total_processed': total_processed,
        'total_skipped': total_skipped,
        'counts': {str(i): len(results[i]) for i in range(7)}
    }

    return {
        'results': {str(i): results[i] for i in range(7)},
        'summary': summary,
        'errors': {k: len(v) for k, v in error_tracker.items() if v}
    }
