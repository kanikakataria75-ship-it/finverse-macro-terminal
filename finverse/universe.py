"""Instrument master: one row per instrument, one source of truth for symbology.

sym     : Yahoo Finance symbol (primary key)
code    : terminal display code
cls     : index | equity | fx | rate | commodity | crypto | etf | sector | vol
iso3    : country (for the world map)
binance : live spot symbol on Binance (crypto only)
"""
from dataclasses import dataclass, field, asdict


@dataclass
class Inst:
    sym: str
    code: str
    name: str
    cls: str
    iso3: str = ""
    region: str = ""
    ccy: str = "USD"
    binance: str = ""
    aliases: list = field(default_factory=list)
    tape: bool = False  # appears on the top ticker tape


I = Inst
UNIVERSE: list[Inst] = [
    # --- Americas indices
    I("^GSPC", "SPX", "S&P 500", "index", "USA", "AMER", tape=True, aliases=["s&p", "sp500", "spx", "wall street"]),
    I("^IXIC", "CCMP", "Nasdaq Composite", "index", "USA", "AMER", tape=True, aliases=["nasdaq"]),
    I("^DJI", "INDU", "Dow Jones Industrial", "index", "USA", "AMER", tape=True, aliases=["dow"]),
    I("^RUT", "RTY", "Russell 2000", "index", "USA", "AMER", aliases=["russell", "small caps"]),
    I("^GSPTSE", "SPTSX", "S&P/TSX Composite", "index", "CAN", "AMER", "CAD", aliases=["tsx", "canada"]),
    I("^BVSP", "IBOV", "Bovespa", "index", "BRA", "AMER", "BRL", aliases=["bovespa", "brazil"]),
    I("^MXX", "MEXBOL", "IPC Mexico", "index", "MEX", "AMER", "MXN", aliases=["mexico"]),
    I("^MERV", "MERVAL", "Merval", "index", "ARG", "AMER", "ARS", aliases=["argentina"]),
    # --- EMEA indices
    I("^FTSE", "UKX", "FTSE 100", "index", "GBR", "EMEA", "GBP", tape=True, aliases=["ftse", "uk stocks"]),
    I("^GDAXI", "DAX", "DAX", "index", "DEU", "EMEA", "EUR", tape=True, aliases=["dax", "germany"]),
    I("^FCHI", "CAC", "CAC 40", "index", "FRA", "EMEA", "EUR", aliases=["cac", "france"]),
    I("^STOXX50E", "SX5E", "Euro Stoxx 50", "index", "", "EMEA", "EUR", aliases=["stoxx", "europe"]),
    I("FTSEMIB.MI", "FTSEMIB", "FTSE MIB", "index", "ITA", "EMEA", "EUR", aliases=["italy"]),
    I("^IBEX", "IBEX", "IBEX 35", "index", "ESP", "EMEA", "EUR", aliases=["spain"]),
    I("^SSMI", "SMI", "Swiss Market Index", "index", "CHE", "EMEA", "CHF", aliases=["swiss", "switzerland"]),
    I("^AEX", "AEX", "AEX", "index", "NLD", "EMEA", "EUR", aliases=["netherlands", "dutch"]),
    I("XU100.IS", "XU100", "BIST 100", "index", "TUR", "EMEA", "TRY", aliases=["turkey", "borsa istanbul"]),
    I("^TA125.TA", "TA125", "TA-125", "index", "ISR", "EMEA", "ILS", aliases=["israel", "tel aviv"]),
    # --- APAC indices
    I("^N225", "NKY", "Nikkei 225", "index", "JPN", "APAC", "JPY", tape=True, aliases=["nikkei", "japan"]),
    I("^HSI", "HSI", "Hang Seng", "index", "HKG", "APAC", "HKD", tape=True, aliases=["hang seng", "hong kong"]),
    I("000001.SS", "SHCOMP", "Shanghai Composite", "index", "CHN", "APAC", "CNY", aliases=["shanghai", "china stocks"]),
    I("^KS11", "KOSPI", "KOSPI", "index", "KOR", "APAC", "KRW", aliases=["kospi", "korea"]),
    I("^TWII", "TWSE", "Taiwan Weighted", "index", "TWN", "APAC", "TWD", aliases=["taiwan"]),
    I("^AXJO", "AS51", "S&P/ASX 200", "index", "AUS", "APAC", "AUD", aliases=["asx", "australia"]),
    I("^NZ50", "NZX50", "NZX 50", "index", "NZL", "APAC", "NZD", aliases=["new zealand"]),
    I("^JKSE", "JCI", "Jakarta Composite", "index", "IDN", "APAC", "IDR", aliases=["indonesia"]),
    I("^STI", "STI", "Straits Times", "index", "SGP", "APAC", "SGD", aliases=["singapore"]),
    I("^KLSE", "FBMKLCI", "FTSE Bursa Malaysia", "index", "MYS", "APAC", "MYR", aliases=["malaysia"]),
    # --- India
    I("^NSEI", "NIFTY", "Nifty 50", "index", "IND", "INDIA", "INR", tape=True, aliases=["nifty", "nifty50", "india stocks"]),
    I("^BSESN", "SENSEX", "BSE Sensex", "index", "", "INDIA", "INR", tape=True, aliases=["sensex"]),
    I("^NSEBANK", "BANKNIFTY", "Nifty Bank", "sector", "", "INDIA", "INR", tape=True, aliases=["bank nifty", "banknifty", "banks"]),
    I("^CNXIT", "NIFTYIT", "Nifty IT", "sector", "", "INDIA", "INR", aliases=["it sector", "nifty it", "tech"]),
    I("^CNXPHARMA", "NIFTYPHARMA", "Nifty Pharma", "sector", "", "INDIA", "INR", aliases=["pharma"]),
    I("AUTOBEES.NS", "NIFTYAUTO", "Nifty Auto (ETF proxy)", "sector", "", "INDIA", "INR", aliases=["auto", "autos"]),
    I("FMCGIETF.NS", "NIFTYFMCG", "Nifty FMCG (ETF proxy)", "sector", "", "INDIA", "INR", aliases=["fmcg", "consumer"]),
    I("METALIETF.NS", "NIFTYMETAL", "Nifty Metal (ETF proxy)", "sector", "", "INDIA", "INR", aliases=["metals", "metal"]),
    I("MOREALTY.NS", "NIFTYREALTY", "Nifty Realty (ETF proxy)", "sector", "", "INDIA", "INR", aliases=["realty", "real estate"]),
    I("ENERGY.NS", "NIFTYENERGY", "Nifty Energy (ETF proxy)", "sector", "", "INDIA", "INR", aliases=["energy"]),
    I("PSUBNKBEES.NS", "NIFTYPSUBANK", "Nifty PSU Bank (ETF proxy)", "sector", "", "INDIA", "INR", aliases=["psu bank"]),
    I("FINIETF.NS", "FINNIFTY", "Nifty Financial Services (ETF proxy)", "sector", "", "INDIA", "INR", aliases=["finnifty", "financials"]),
    I("^INDIAVIX", "INVIX", "India VIX", "vol", "", "INDIA", "INR", tape=True, aliases=["india vix"]),
    # India large caps
    I("RELIANCE.NS", "RELIANCE", "Reliance Industries", "equity", "", "INDIA", "INR", aliases=["reliance", "ril"]),
    I("TCS.NS", "TCS", "Tata Consultancy Services", "equity", "", "INDIA", "INR", aliases=["tcs"]),
    I("HDFCBANK.NS", "HDFCBANK", "HDFC Bank", "equity", "", "INDIA", "INR", aliases=["hdfc bank", "hdfc"]),
    I("ICICIBANK.NS", "ICICIBANK", "ICICI Bank", "equity", "", "INDIA", "INR", aliases=["icici"]),
    I("INFY.NS", "INFY", "Infosys", "equity", "", "INDIA", "INR", aliases=["infosys", "infy"]),
    I("SBIN.NS", "SBIN", "State Bank of India", "equity", "", "INDIA", "INR", aliases=["sbi", "state bank"]),
    I("BHARTIARTL.NS", "BHARTIARTL", "Bharti Airtel", "equity", "", "INDIA", "INR", aliases=["airtel", "bharti"]),
    I("ITC.NS", "ITC", "ITC", "equity", "", "INDIA", "INR", aliases=["itc"]),
    I("LT.NS", "LT", "Larsen & Toubro", "equity", "", "INDIA", "INR", aliases=["larsen", "l&t"]),
    I("HINDUNILVR.NS", "HINDUNILVR", "Hindustan Unilever", "equity", "", "INDIA", "INR", aliases=["hul", "hindustan unilever"]),
    I("BAJFINANCE.NS", "BAJFINANCE", "Bajaj Finance", "equity", "", "INDIA", "INR", aliases=["bajaj finance"]),
    I("ASIANPAINT.NS", "ASIANPAINT", "Asian Paints", "equity", "", "INDIA", "INR", aliases=["asian paints"]),
    I("MARUTI.NS", "MARUTI", "Maruti Suzuki", "equity", "", "INDIA", "INR", aliases=["maruti"]),
    I("SUNPHARMA.NS", "SUNPHARMA", "Sun Pharma", "equity", "", "INDIA", "INR", aliases=["sun pharma"]),
    I("ONGC.NS", "ONGC", "ONGC", "equity", "", "INDIA", "INR", aliases=["ongc"]),
    I("BPCL.NS", "BPCL", "Bharat Petroleum", "equity", "", "INDIA", "INR", aliases=["bpcl"]),
    I("IOC.NS", "IOC", "Indian Oil Corp", "equity", "", "INDIA", "INR", aliases=["indian oil", "ioc"]),
    I("TATASTEEL.NS", "TATASTEEL", "Tata Steel", "equity", "", "INDIA", "INR", aliases=["tata steel"]),
    I("ADANIENT.NS", "ADANIENT", "Adani Enterprises", "equity", "", "INDIA", "INR", aliases=["adani"]),
    I("AXISBANK.NS", "AXISBANK", "Axis Bank", "equity", "", "INDIA", "INR", aliases=["axis bank"]),
    I("KOTAKBANK.NS", "KOTAKBANK", "Kotak Mahindra Bank", "equity", "", "INDIA", "INR", aliases=["kotak"]),
    I("WIPRO.NS", "WIPRO", "Wipro", "equity", "", "INDIA", "INR", aliases=["wipro"]),
    I("HCLTECH.NS", "HCLTECH", "HCL Technologies", "equity", "", "INDIA", "INR", aliases=["hcl"]),
    I("NTPC.NS", "NTPC", "NTPC", "equity", "", "INDIA", "INR", aliases=["ntpc"]),
    I("COALINDIA.NS", "COALINDIA", "Coal India", "equity", "", "INDIA", "INR", aliases=["coal india"]),
    I("TITAN.NS", "TITAN", "Titan Company", "equity", "", "INDIA", "INR", aliases=["titan"]),
    I("INDIGO.NS", "INDIGO", "InterGlobe Aviation", "equity", "", "INDIA", "INR", aliases=["indigo", "interglobe"]),
    I("ULTRACEMCO.NS", "ULTRACEMCO", "UltraTech Cement", "equity", "", "INDIA", "INR", aliases=["ultratech"]),
    # --- US mega caps
    I("AAPL", "AAPL", "Apple", "equity", "", "US", aliases=["apple"]),
    I("MSFT", "MSFT", "Microsoft", "equity", "", "US", aliases=["microsoft"]),
    I("NVDA", "NVDA", "NVIDIA", "equity", "", "US", tape=True, aliases=["nvidia"]),
    I("GOOGL", "GOOGL", "Alphabet", "equity", "", "US", aliases=["google", "alphabet"]),
    I("AMZN", "AMZN", "Amazon", "equity", "", "US", aliases=["amazon"]),
    I("META", "META", "Meta Platforms", "equity", "", "US", aliases=["meta", "facebook"]),
    I("TSLA", "TSLA", "Tesla", "equity", "", "US", aliases=["tesla"]),
    I("AVGO", "AVGO", "Broadcom", "equity", "", "US", aliases=["broadcom"]),
    I("TSM", "TSM", "Taiwan Semiconductor", "equity", "", "US", aliases=["tsmc"]),
    I("JPM", "JPM", "JPMorgan Chase", "equity", "", "US", aliases=["jpmorgan"]),
    I("XOM", "XOM", "Exxon Mobil", "equity", "", "US", aliases=["exxon"]),
    # --- Rates (Yahoo quotes yields x1)
    I("^IRX", "US3M", "US 13-Week Bill", "rate", "", "RATES", aliases=["3 month", "t-bill"]),
    I("^FVX", "US5Y", "US 5Y Yield", "rate", "", "RATES", aliases=["5 year"]),
    I("^TNX", "US10Y", "US 10Y Yield", "rate", "", "RATES", tape=True, aliases=["10 year", "treasury", "yields", "bond yields"]),
    I("^TYX", "US30Y", "US 30Y Yield", "rate", "", "RATES", aliases=["30 year"]),
    # --- FX
    I("DX-Y.NYB", "DXY", "US Dollar Index", "fx", "", "FX", tape=True, aliases=["dxy", "dollar index", "dollar"]),
    I("EURUSD=X", "EURUSD", "EUR/USD", "fx", "", "FX", tape=True, aliases=["euro", "eurusd"]),
    I("JPY=X", "USDJPY", "USD/JPY", "fx", "", "FX", tape=True, aliases=["yen", "usdjpy"]),
    I("GBPUSD=X", "GBPUSD", "GBP/USD", "fx", "", "FX", aliases=["pound", "sterling", "cable"]),
    I("INR=X", "USDINR", "USD/INR", "fx", "", "FX", "INR", tape=True, aliases=["rupee", "inr", "usdinr"]),
    I("CNY=X", "USDCNY", "USD/CNY", "fx", "", "FX", aliases=["yuan", "renminbi"]),
    I("AUDUSD=X", "AUDUSD", "AUD/USD", "fx", "", "FX", aliases=["aussie"]),
    I("CHF=X", "USDCHF", "USD/CHF", "fx", "", "FX", aliases=["franc"]),
    I("CAD=X", "USDCAD", "USD/CAD", "fx", "", "FX", aliases=["loonie"]),
    I("BRL=X", "USDBRL", "USD/BRL", "fx", "", "FX", aliases=["real"]),
    I("MXN=X", "USDMXN", "USD/MXN", "fx", "", "FX", aliases=["peso"]),
    I("KRW=X", "USDKRW", "USD/KRW", "fx", "", "FX", aliases=["won"]),
    I("TRY=X", "USDTRY", "USD/TRY", "fx", "", "FX", aliases=["lira"]),
    I("ZAR=X", "USDZAR", "USD/ZAR", "fx", "", "FX", aliases=["rand"]),
    # --- Commodities
    I("CL=F", "WTI", "WTI Crude", "commodity", "", "COMDTY", tape=True, aliases=["wti", "crude", "oil"]),
    I("BZ=F", "BRENT", "Brent Crude", "commodity", "", "COMDTY", tape=True, aliases=["brent", "brent crude"]),
    I("NG=F", "NATGAS", "Natural Gas", "commodity", "", "COMDTY", aliases=["natural gas", "natgas", "lng"]),
    I("GC=F", "GOLD", "Gold", "commodity", "", "COMDTY", tape=True, aliases=["gold", "bullion"]),
    I("SI=F", "SILVER", "Silver", "commodity", "", "COMDTY", tape=True, aliases=["silver"]),
    I("HG=F", "COPPER", "Copper", "commodity", "", "COMDTY", tape=True, aliases=["copper", "dr copper"]),
    I("PL=F", "PLAT", "Platinum", "commodity", "", "COMDTY", aliases=["platinum"]),
    I("ZW=F", "WHEAT", "Wheat", "commodity", "", "COMDTY", aliases=["wheat"]),
    I("ZC=F", "CORN", "Corn", "commodity", "", "COMDTY", aliases=["corn"]),
    I("ZS=F", "SOY", "Soybeans", "commodity", "", "COMDTY", aliases=["soybeans", "soy"]),
    I("KC=F", "COFFEE", "Coffee", "commodity", "", "COMDTY", aliases=["coffee"]),
    I("SB=F", "SUGAR", "Sugar", "commodity", "", "COMDTY", aliases=["sugar"]),
    # --- Crypto (live via Binance, Yahoo for history)
    I("BTC-USD", "BTC", "Bitcoin", "crypto", "", "CRYPTO", binance="BTCUSDT", tape=True, aliases=["bitcoin", "btc", "btcusd"]),
    I("ETH-USD", "ETH", "Ethereum", "crypto", "", "CRYPTO", binance="ETHUSDT", tape=True, aliases=["ethereum", "eth"]),
    I("SOL-USD", "SOL", "Solana", "crypto", "", "CRYPTO", binance="SOLUSDT", tape=True, aliases=["solana", "sol"]),
    I("BNB-USD", "BNB", "BNB", "crypto", "", "CRYPTO", binance="BNBUSDT", aliases=["bnb", "binance coin"]),
    I("XRP-USD", "XRP", "XRP", "crypto", "", "CRYPTO", binance="XRPUSDT", aliases=["xrp", "ripple"]),
    I("DOGE-USD", "DOGE", "Dogecoin", "crypto", "", "CRYPTO", binance="DOGEUSDT", aliases=["dogecoin", "doge"]),
    # --- Volatility & cross-asset ETFs (used by analytics)
    I("^VIX", "VIX", "CBOE VIX", "vol", "", "US", tape=True, aliases=["vix", "fear index", "volatility"]),
    I("SPY", "SPY", "SPDR S&P 500 ETF", "etf", "", "US"),
    I("RSP", "RSP", "Equal-Weight S&P 500 ETF", "etf", "", "US"),
    I("QQQ", "QQQ", "Invesco QQQ", "etf", "", "US"),
    I("TLT", "TLT", "20Y+ Treasury ETF", "etf", "", "US", aliases=["long bonds"]),
    I("IEF", "IEF", "7-10Y Treasury ETF", "etf", "", "US"),
    I("TIP", "TIP", "TIPS ETF", "etf", "", "US", aliases=["tips", "inflation protected"]),
    I("HYG", "HYG", "High Yield Corp Bond ETF", "etf", "", "US", aliases=["junk bonds", "high yield"]),
    I("EEM", "EEM", "Emerging Markets ETF", "etf", "", "US", aliases=["emerging markets"]),
    I("INDA", "INDA", "MSCI India ETF", "etf", "", "US"),
    I("XLK", "XLK", "US Technology", "etf", "", "USSECT"),
    I("XLF", "XLF", "US Financials", "etf", "", "USSECT"),
    I("XLE", "XLE", "US Energy", "etf", "", "USSECT"),
    I("XLV", "XLV", "US Health Care", "etf", "", "USSECT"),
    I("XLI", "XLI", "US Industrials", "etf", "", "USSECT"),
    I("XLY", "XLY", "US Cons. Discretionary", "etf", "", "USSECT"),
    I("XLP", "XLP", "US Cons. Staples", "etf", "", "USSECT"),
    I("XLU", "XLU", "US Utilities", "etf", "", "USSECT"),
    I("XLB", "XLB", "US Materials", "etf", "", "USSECT"),
    I("XLRE", "XLRE", "US Real Estate", "etf", "", "USSECT"),
    I("XLC", "XLC", "US Communication", "etf", "", "USSECT"),
]

BY_SYM = {i.sym: i for i in UNIVERSE}
BY_CODE = {i.code: i for i in UNIVERSE}
BY_BINANCE = {i.binance: i for i in UNIVERSE if i.binance}
SYMBOLS = [i.sym for i in UNIVERSE]

# Country -> benchmark index (world equity map)
COUNTRY_INDEX = {i.iso3: i.sym for i in UNIVERSE if i.iso3 and i.cls == "index"}
# Country -> currency pair quoted as USD/XXX (up = local currency weaker)
COUNTRY_FX = {
    "IND": "INR=X", "JPN": "JPY=X", "CHN": "CNY=X", "CHE": "CHF=X", "CAN": "CAD=X",
    "BRA": "BRL=X", "MEX": "MXN=X", "KOR": "KRW=X", "TUR": "TRY=X", "ZAF": "ZAR=X",
}
EURO_AREA = ["DEU", "FRA", "ITA", "ESP", "NLD", "BEL", "AUT", "PRT", "IRL", "FIN", "GRC"]

# Transmission model: global drivers -> Indian sectors
DRIVERS = ["BZ=F", "DX-Y.NYB", "^TNX", "INR=X", "^IXIC", "GC=F"]
INDIA_TARGETS = [
    "^NSEI", "^NSEBANK", "^CNXIT", "^CNXPHARMA", "AUTOBEES.NS", "FMCGIETF.NS", "METALIETF.NS",
    "MOREALTY.NS", "ENERGY.NS", "PSUBNKBEES.NS", "FINIETF.NS",
    "ASIANPAINT.NS", "BPCL.NS", "INDIGO.NS", "RELIANCE.NS", "TCS.NS",
]

# Default macro asset matrix on the MACRO workspace (left column)
MATRIX = ["GC=F", "SI=F", "BTC-USD", "EURUSD=X", "JPY=X", "INR=X", "DX-Y.NYB", "^VIX", "BZ=F", "^TNX"]


EXTRA_NAMES: dict[str, str] = {}  # symbols found via search at runtime -> display name


def meta(sym: str) -> dict:
    i = BY_SYM.get(sym)
    if i:
        return asdict(i)
    return {"sym": sym, "code": sym.split(".")[0].lstrip("^"), "name": EXTRA_NAMES.get(sym, sym), "cls": "equity",
            "ccy": "INR" if sym.endswith((".NS", ".BO")) else "USD"}


def all_meta() -> list[dict]:
    return [asdict(i) for i in UNIVERSE]


def resolve(text: str) -> str | None:
    """Map free text ('reliance', 'NIFTY', 'btc', 'AAPL') to a Yahoo symbol."""
    t = text.strip()
    if not t:
        return None
    up = t.upper()
    if up in BY_SYM:
        return up
    if t in BY_SYM:
        return t
    if up in BY_CODE:
        return BY_CODE[up].sym
    low = t.lower()
    for i in UNIVERSE:
        if low == i.name.lower() or low in i.aliases:
            return i.sym
    return None
