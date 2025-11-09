import json
from typing import TypedDict, List, Dict
import pandas as pd
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import jieba
import os
from datetime import datetime
import pymongo
import re
from eventregistry import *

load_dotenv()
jieba.initialize()

def sanitize_collection_name(keyword):
    """Convert keyword to a valid MongoDB collection name"""
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', keyword)
    if sanitized and sanitized[0].isdigit():
        sanitized = 'col_' + sanitized
    if not sanitized:
        sanitized = 'news'
    return sanitized.lower()

def store_news_with_user_keyword():
    # Get keyword from user
    keyword = input("Enter keyword to search for: ").strip()
    if not keyword:
        keyword = "news"
    
    collection_name = sanitize_collection_name(keyword)
    
    print(f"Searching for: '{keyword}'")
    print(f"Collection: '{collection_name}'")
    
    # MongoDB connection
    try:
        client = pymongo.MongoClient('mongodb+srv://ya2578_db_user:HackNation@hacknation.ddavo00.mongodb.net/')
        db = client["hacknation"]
        collection = db[collection_name]
        print("Connected to MongoDB Atlas")
        
    except Exception as e:
        print(f"Connection error: {e}")
        return

    # EventRegistry API
    er = EventRegistry(apiKey="9fc75c9a-064d-4b53-a4be-f09ed3b04c45")
    
    # Query with user's keyword
    qStr = f"""
    {{
        "$query": {{
            "$and": [
                {{
                "lang": "eng",
                "keyword": "{keyword}"
                    
                }}
            ]
        }}
    }}
    """
    
    try:
        q = QueryArticlesIter.initWithComplexQuery(qStr)
        i = 0
        articles_data = []  # Store article data for summarization
        
        for article in q.execQuery(er):
            try:
                doc = {
                    "title": article.get("title"),
                    "body": article.get("body"),
                    "type": "article",

                }
                
                result = collection.insert_one(doc)
                articles_data.append({
                    "title": article.get("title"),
                    "body": article.get("body"),
                    "id": str(result.inserted_id)
                })
                print(f"Inserted: {article.get('title', 'No title')[:50]}...")
                i += 1
                
            except Exception as e:
                print(f"Error: {e}")
                
            if i >= 10:
                break
                
        print(f"\nStored {i} articles in '{collection_name}'")
        
        # Generate summary using LLM
        if articles_data:
            print("🤖 Generating summary with LLM...")
            summary = generate_news_summary(articles_data, keyword)
            
            # Store summary as 11th element
            summary_doc = {
                "title": f"AI Summary: {keyword}",
                "body": summary,
                "type": "summary",
                "keyword": keyword,
                "article_count": len(articles_data),
            }
            
            collection.insert_one(summary_doc)
            print("✅ Summary stored as 11th element in collection")
            print(f"📝 Summary preview: {summary[:100]}...")
        
    except Exception as e:
        print(f"Query error: {e}")

    client.close()

# LLM Summarization Components
class SummaryState(TypedDict):
    messages: List[BaseMessage]
    articles_data: List[Dict]
    keyword: str
    summary: str

# Load and validate OpenAI / LLM environment variables
API_KEY = os.getenv("API_KEY")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE")  # e.g. https://api.openai.com/v1 or your Azure/hosted base
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

if not API_KEY:
    raise RuntimeError(
        "Missing API_KEY environment variable. Add it to your .env or export it in your shell."
    )

# Instantiate the ChatOpenAI client. If you actually intend to use Anthropic/Claude,
# use the Anthropic client instead — mixing an Anthropic model name with ChatOpenAI
# will not work correctly.
llm = ChatOpenAI(
    openai_api_key=API_KEY,
    openai_api_base=OPENAI_API_BASE or "https://api.openai.com/v1",
    model_name=OPENAI_MODEL,
)

def create_summary_prompt(state: SummaryState) -> SummaryState:
    """Create system prompt for news summarization"""
    system_message = SystemMessage(content=
        """You are an expert news analyst and summarizer. Your task is to analyze multiple news articles about a specific topic and provide a concise, insightful summary.

Key requirements:
- Focus on the main themes and patterns across all articles
- Identify any consensus or conflicting viewpoints
- Highlight key facts, events, or developments
- Keep the summary concise but comprehensive (200-300 words)
- Maintain an objective, analytical tone
- Extract the most important information that would be valuable for someone researching this topic"""
    )
    return {"messages": [system_message]}

def prepare_articles_content(state: SummaryState) -> SummaryState:
    """Prepare the articles content for the LLM"""
    articles = state["articles_data"]
    keyword = state["keyword"]
    
    # Format articles for the prompt
    articles_content = []
    for i, article in enumerate(articles, 1):
        content = f"ARTICLE {i}:\n"
        content += f"Title: {article.get('title', 'No title')}\n"
        content += f"Content: {article.get('body', 'No content available')}\n"
        content += "-" * 50
        articles_content.append(content)
    
    full_content = "\n\n".join(articles_content)
    
    human_message = HumanMessage(content=f"""
TOPIC/KEYWORD: {keyword}

NUMBER OF ARTICLES: {len(articles)}

ARTICLES CONTENT:
{full_content}

INSTRUCTIONS:
Please analyze these {len(articles)} articles about "{keyword}" and provide a comprehensive summary that:
1. Identifies the main themes and patterns
2. Highlights key information and developments
3. Notes any consensus or disagreements between sources
4. Provides overall insights about the topic based on these articles

Your summary should be concise (200-300 words) but capture the essential information from all articles.
""")
    
    return {"messages": state["messages"] + [human_message]}

def generate_summary(state: SummaryState) -> SummaryState:
    """Generate the summary using LLM"""
    messages = state["messages"]
    
    response = llm.invoke(messages)
    summary = response.content
    
    return {"summary": summary}

# Create the summarization workflow
summary_workflow = StateGraph(SummaryState)

summary_workflow.add_node("create_summary_prompt", create_summary_prompt)
summary_workflow.add_node("prepare_articles_content", prepare_articles_content)
summary_workflow.add_node("generate_summary", generate_summary)

summary_workflow.add_edge("create_summary_prompt", "prepare_articles_content")
summary_workflow.add_edge("prepare_articles_content", "generate_summary")
summary_workflow.add_edge("generate_summary", END)

summary_workflow.set_entry_point("create_summary_prompt")

summary_app = summary_workflow.compile()

def generate_news_summary(articles_data: List[Dict], keyword: str) -> str:
    """Generate summary for news articles"""
    results = summary_app.invoke({
        "articles_data": articles_data,
        "keyword": keyword,
        "messages": [],
        "summary": ""
    })
    return results["summary"]



if __name__ == "__main__":
    # Run the news collection and summarization
    store_news_with_user_keyword()
    
   