import asyncio
from harvesters import fetch_quantitative_data, fetch_qualitative_news

async def main():
    ticker = "AAPL" # Apple Inc.
    
    print("\n--- Testing Quantitative Harvester ---")
    financials = await fetch_quantitative_data(ticker)
    print(financials)
    
    print("\n--- Testing Qualitative Harvester ---")
    news = await fetch_qualitative_news(ticker)
    print(news[:500] + "...\n[Printed first 500 chars for brevity]")
    
    print("\nDone! Harvesters are fully operational.")

if __name__ == "__main__":
    asyncio.run(main())