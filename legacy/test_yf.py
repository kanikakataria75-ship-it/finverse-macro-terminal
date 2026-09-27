import yfinance as yf

for ticker in ["BZ=F", "^IXIC", "BTC-USD"]:
    stock = yf.Ticker(ticker)
    hist = stock.history(period="1mo")
    hist_live = stock.history(period="1d", interval="1m")
    
    current_price_daily = hist['Close'].iloc[-1] if not hist.empty else None
    current_price_live = hist_live['Close'].iloc[-1] if not hist_live.empty else None
    
    print(f"{ticker}: Daily Last: {current_price_daily}, Live 1m Last: {current_price_live}")
