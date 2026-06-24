import asyncio
from agent import app_graph

async def main():
    ticker = "NVDA" # Testing Nvidia this time!
    
    print("🚀 Initializing LangGraph Multi-Agent Pipeline...\n")
    
    initial_state = {
        "ticker": ticker,
        "raw_financials": {},
        "scraped_articles": "",
        "final_markdown_report": "",
        "error": ""
    }
    
    # Run the graph
    final_state = await app_graph.ainvoke(initial_state)
    
    print("\n" + "="*50)
    print("📈 FINAL SYNTHESIZED REPORT 📈")
    print("="*50 + "\n")
    print(final_state["final_markdown_report"])
    print("\n" + "="*50)

if __name__ == "__main__":
    asyncio.run(main())