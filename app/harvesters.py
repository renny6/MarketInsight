import yfinance as yf
from newspaper import Article
import logging
import asyncio

# Set up logging so we can see what's happening in the terminal
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global lock to serialize yfinance requests and prevent race conditions
yfinance_lock = asyncio.Lock()

async def fetch_quantitative_data(ticker: str) -> dict:
    """Fetches raw financial numbers using yfinance with robust fallbacks."""
    logger.info(f"Fetching financial data for {ticker}...")
    try:
        async with yfinance_lock:
            stock = await asyncio.to_thread(yf.Ticker, ticker)
            
            # 1. Try to fetch basic info
            info = {}
            try:
                fetched_info = await asyncio.to_thread(lambda: stock.info)
                if isinstance(fetched_info, dict):
                    info = fetched_info
            except Exception as info_err:
                logger.warning(f"Failed to fetch stock.info for {ticker}: {info_err}")
            
            # 2. Try to fetch fast_info as fallback
            fast_info = {}
            try:
                fetched_fast = await asyncio.to_thread(lambda: stock.fast_info)
                if fetched_fast:
                    fast_info = dict(fetched_fast)
            except Exception as fast_err:
                logger.warning(f"Failed to fetch stock.fast_info for {ticker}: {fast_err}")
                
            # 3. Try to fetch history for price fallback
            history_price = None
            if not info.get("currentPrice") and not fast_info.get("lastPrice"):
                try:
                    df = await asyncio.to_thread(stock.history, period="1d")
                    if not df.empty:
                        history_price = float(df["Close"].iloc[-1])
                except Exception as hist_err:
                    logger.warning(f"Failed to fetch stock history for {ticker}: {hist_err}")

        # 4. Resolve company name
        company_name = (
            info.get("longName") or 
            info.get("shortName") or 
            info.get("displayName") or 
            ticker
        )
        
        # 5. Resolve current price
        current_price = (
            info.get("currentPrice") or 
            info.get("regularMarketPrice") or 
            info.get("lastPrice") or 
            info.get("navPrice") or 
            fast_info.get("lastPrice") or 
            history_price or 
            "N/A"
        )
        if current_price != "N/A":
            current_price = round(float(current_price), 2)
            
        # 6. Resolve market cap
        market_cap = (
            info.get("marketCap") or 
            info.get("totalAssets") or 
            info.get("netAssets") or 
            fast_info.get("marketCap") or 
            "N/A"
        )
        
        # 7. Resolve P/E Ratio
        pe_ratio = info.get("trailingPE") or info.get("forwardPE") or "N/A"
        # Calculate manually if possible
        if pe_ratio == "N/A" and current_price != "N/A":
            eps = info.get("trailingEps") or info.get("forwardEps")
            if eps and float(eps) != 0:
                pe_ratio = round(float(current_price) / float(eps), 2)
                
        # 8. Resolve 52-week High/Low
        fifty_two_week_high = (
            info.get("fiftyTwoWeekHigh") or 
            fast_info.get("yearHigh") or 
            info.get("regularMarketDayHigh") or 
            "N/A"
        )
        if fifty_two_week_high != "N/A":
            fifty_two_week_high = round(float(fifty_two_week_high), 2)
            
        fifty_two_week_low = (
            info.get("fiftyTwoWeekLow") or 
            fast_info.get("yearLow") or 
            info.get("regularMarketDayLow") or 
            "N/A"
        )
        if fifty_two_week_low != "N/A":
            fifty_two_week_low = round(float(fifty_two_week_low), 2)
            
        data = {
            "ticker": ticker,
            "company_name": company_name,
            "current_price": current_price,
            "market_cap": market_cap,
            "pe_ratio": pe_ratio,
            "52_week_high": fifty_two_week_high,
            "52_week_low": fifty_two_week_low
        }
        return data
    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        return {"error": str(e)}

async def fetch_qualitative_news(ticker: str) -> str:
    """Scrapes recent news articles for the AI to analyze, with strict limits."""
    logger.info(f"Fetching news for {ticker}...")
    try:
        async with yfinance_lock:
            stock = await asyncio.to_thread(yf.Ticker, ticker)
            news_items = await asyncio.to_thread(lambda: stock.news)
            
        if not news_items:
            news_items = []
        else:
            news_items = news_items[:3] # Grab top 3 recent articles
            
        combined_text = f"Recent news for {ticker}:\n\n"
        
        for item in news_items:
            url = item.get("link")
            if url:
                try:
                    # Newspaper3k extracts the main text from news websites
                    article = Article(url)
                    await asyncio.to_thread(article.download)
                    await asyncio.to_thread(article.parse)
                    
                    combined_text += f"Title: {item.get('title')}\n"
                    combined_text += f"Content: {article.text}\n\n"
                except Exception as e:
                    logger.warning(f"Could not scrape {url}: {e}")
        
        # --- ARCHITECTURE MANDATE: STRICT CONTEXT WINDOW LIMIT ---
        # Enforce 6,000 character limit for free-tier LLM compatibility
        if len(combined_text) > 6000:
            logger.info(f"Truncating news payload from {len(combined_text)} to 6000 characters.")
            combined_text = combined_text[:6000] + "\n...[TRUNCATED FOR CONTEXT WINDOW]"
            
        return combined_text
    except Exception as e:
        logger.error(f"Error fetching news for {ticker}: {e}")
        return f"Error fetching news: {e}"