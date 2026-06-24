import asyncio
from typing import TypedDict, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()
# Import our harvesters
from app.harvesters import fetch_quantitative_data, fetch_qualitative_news

# --- ARCHITECTURE MANDATE: Free-Tier Rate Limit Throttling ---
# Prevents HTTP 429 crashes when running background cron jobs
llm_semaphore = asyncio.Semaphore(2)

# Define the Global State that passes between nodes
class ReportState(TypedDict):
    ticker: str
    raw_financials: Dict[str, Any]
    scraped_articles: str
    final_markdown_report: str
    error: str

# Define the Strict JSON Schema for Gemini
class FinalReportSchema(BaseModel):
    markdown_report: str = Field(description="The final integrated analysis report in Markdown format")

# --- NODE 1: Orchestrator ---
async def orchestrator_node(state: ReportState):
    print(f"[Node 1] Orchestrating pipeline for {state['ticker']}...")
    return {"error": ""} # Initialize error state

# --- NODE 2: Financial Harvester ---
async def financial_harvester_node(state: ReportState):
    print("[Node 2] Harvesting quantitative data...")
    data = await fetch_quantitative_data(state["ticker"])
    if "error" in data:
        return {"error": data["error"]}
    return {"raw_financials": data}

# --- NODE 3: Scraper & Filter ---
async def scraper_node(state: ReportState):
    if state.get("error"): return {}
    print("[Node 3] Scraping qualitative news...")
    news = await fetch_qualitative_news(state["ticker"])
    return {"scraped_articles": news}

# --- NODE 4: Synthesis & Formatter ---
async def synthesis_node(state: ReportState):
    if state.get("error"): 
        return {"final_markdown_report": f"Error: {state['error']}"}
        
    print("[Node 4] Synthesizing data with Google Gemini...")
    
    # Initialize Gemini
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.2)
    # Architecture Mandate: Strict JSON Structure Output
    structured_llm = llm.with_structured_output(FinalReportSchema)
    
    sys_prompt = """You are an institutional equity research analyst. You are given two datasets:
    1. QUANTITATIVE: Balance sheets, financial margins, and historical valuations.
    2. QUALITATIVE: Clean, full-text scraped articles.

    You must build an Integrated Analysis report in Markdown format. 

    CRITICAL MANDATE:
    The report MUST start with a '## Quantitative Overview' section. In this section, present the key financial metrics (Price, Market Cap, P/E ratio, and 52-week range) in a structured markdown table or a clean bulleted list using the provided QUANTITATIVE DATA. If any metric is "N/A", list it as "N/A".

    If the <SCRAPED_DATA> contains readable news, map it to the financials using this structure:
    "Breaking news indicates [Qualitative Event Summary]. This directly impacts the company's [Quantitative Metric], which currently sits at [Value]."

    CRITICAL FALLBACK INSTRUCTION:
    If the text inside <SCRAPED_DATA> is empty, too short, or looks like an error, DO NOT leave the report blank. Instead, ignore the news entirely and write a detailed 2-paragraph fundamental analysis based strictly on the raw QUANTITATIVE numbers provided (Market Cap, P/E ratio, etc.).
    """
    
    user_prompt = f"""
    QUANTITATIVE DATA:
    {state['raw_financials']}
    
    QUALITATIVE DATA:
    <SCRAPED_DATA>
    {state['scraped_articles']}
    </SCRAPED_DATA>
    """
    
    # Apply the Semaphore Lock
    async with llm_semaphore:
        response = await structured_llm.ainvoke([
            SystemMessage(content=sys_prompt),
            HumanMessage(content=user_prompt)
        ])
        
    return {"final_markdown_report": response.markdown_report}

# --- BUILD THE GRAPH ---
workflow = StateGraph(ReportState)

workflow.add_node("orchestrator", orchestrator_node)
workflow.add_node("financial_harvester", financial_harvester_node)
workflow.add_node("scraper", scraper_node)
workflow.add_node("synthesis", synthesis_node)

workflow.set_entry_point("orchestrator")
workflow.add_edge("orchestrator", "financial_harvester")
workflow.add_edge("financial_harvester", "scraper")
workflow.add_edge("scraper", "synthesis")
workflow.add_edge("synthesis", END)

# Compile the multi-agent graph
app_graph = workflow.compile()