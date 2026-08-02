"""
set50_list.py
-------------
Provides official SET50 and SET100 Index constituents lists for SET-listed stocks
and utility functions for index filtering and sample retrieval.
"""

SET50_TICKERS = [
    "ADVANC", "AOT", "AWC", "BAM", "BANPU", "BBL", "BCH", "BCP", "BCPG", "BDMS",
    "BEM", "BGRIM", "BH", "BLA", "BTS", "CBG", "CENTEL", "CHG", "CK", "COM7",
    "CPALL", "CPAXT", "CPF", "CPN", "CRC", "DELTA", "DOHOME", "EGCO", "GLOBAL", "GPSC",
    "GULF", "HMPRO", "INTUCH", "IVL", "KBANK", "KCE", "KKP", "KTB", "KTC", "LH",
    "MINT", "MTC", "OR", "OSP", "PLANB", "PTT", "PTTEP", "PTTGC", "RATCH", "SAWAD",
    "SCB", "SCC", "SCGP", "TCAP", "TIDLOR", "TISCO", "TLI", "TOP", "TRUE", "TTB",
    "TU", "WHA"
]

SET100_ADDITIONAL_TICKERS = [
    "AAI", "AAV", "ACE", "AEONTS", "AMATA", "AP", "BA", "BBIK", "BE8", "BJC",
    "BLAND", "BTG", "BYD", "CKP", "DITTO", "ERW", "ESSO", "FORTH", "GFPT", "HANA",
    "ICHI", "ITC", "JAS", "JMART", "JMT", "KAMART", "KSL", "MBK", "MC", "MEGA",
    "MOSHI", "NEX", "NSL", "ONEE", "PLANET", "PRM", "PSL", "PTG", "RBF", "RCL",
    "SAPPE", "SNNP", "SPALI", "STA", "STGT", "TASCO", "THANI", "TIPH", "TKN", "TTA"
]

SET100_TICKERS = sorted(list(set(SET50_TICKERS + SET100_ADDITIONAL_TICKERS)))

def get_set50_list(with_suffix=True):
    """Returns list of SET50 tickers, optionally with '.BK' suffix."""
    if with_suffix:
        return [f"{t}.BK" if not t.endswith(".BK") else t for t in SET50_TICKERS]
    return [t.replace(".BK", "") for t in SET50_TICKERS]

def get_set100_list(with_suffix=True):
    """Returns list of SET100 tickers, optionally with '.BK' suffix."""
    if with_suffix:
        return [f"{t}.BK" if not t.endswith(".BK") else t for t in SET100_TICKERS]
    return [t.replace(".BK", "") for t in SET100_TICKERS]

def is_set50(symbol):
    """Checks if a stock symbol is in the SET50 Index."""
    clean_sym = symbol.replace(".BK", "").strip().upper()
    return clean_sym in SET50_TICKERS

def is_set100(symbol):
    """Checks if a stock symbol is in the SET100 Index."""
    clean_sym = symbol.replace(".BK", "").strip().upper()
    return clean_sym in SET100_TICKERS
