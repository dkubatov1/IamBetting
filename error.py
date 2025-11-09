import json
from datetime import datetime
import pymongo
from dotenv import load_dotenv
import os
import re
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from eventregistry import *

load_dotenv()

def sanitize_collection_name(keyword):
    """Convert keyword to a valid MongoDB collection name"""
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', keyword)
    if sanitized and sanitized[0].isdigit():
        sanitized = 'col_' + sanitized
    if not sanitized:
        sanitized = 'news'
    return sanitized.lower()

def store_news_with_user_keywords(keywords):
    # Get 5 keywords from user
    print("Enter 5 keywords to search for (OR operation - articles containing ANY keyword):")
    
    
    collection_name = sanitize_collection_name(keywords[0])
    
 
    
    # MongoDB connection
    try:
        client = pymongo.MongoClient(os.getenv("DB_NAME"))
        db = client["hacknation"]
        collection = db[collection_name]
        print("✅ Connected to MongoDB Atlas")
        
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return None

    # EventRegistry API
    er = EventRegistry(apiKey=os.getenv("API_KEY"))
    
    # Build OR query for all 5 keywords
    or_conditions = ", ".join([f'{{"keyword": "{keyword}"}}' for keyword in keywords])
    qStr = f'''
    {{
        "$query": {{
            "$and": [
                {{"lang": "eng"}},
                {{"$or": [{or_conditions}]}}
            ]
        }}
    }}
    '''
    
    print("Executing OR query...")
    
    try:
        q = QueryArticlesIter.initWithComplexQuery(qStr)
        i = 0
        seen_combinations = set()  # Track unique articles by date and title
        sum_sentiment = 0
        
        for article in q.execQuery(er):
            try:
                article_date = article.get("date")
                article_title = article.get("title", "No title")
                article_id = f"{article_date}_{article_title}"
                
                # Skip if we've already seen this article
                if article_id in seen_combinations:
                    print(f"⏭️  Skipping duplicate: {article_title[:30]}...")
                    continue
                
                # Add to seen set
                seen_combinations.add(article_id)
                
                # Create document
                doc = {
                    "title": article_title,
                    "body": article.get("body"),
                    
                    
                }
                
                # Insert into MongoDB
                result = collection.insert_one(doc)
                print(f"✅ {i+1}. {article_title[:60]}...")
                print(f"   📅 Date: {article_date}")
                
                # Sentiment analysis
                body_text = article.get("body", "")
                if body_text:
                    sid_obj = SentimentIntensityAnalyzer()
                    sentiment_dict = sid_obj.polarity_scores(body_text)
                    sum_sentiment += sentiment_dict['compound']
                    print(f"   📊 Sentiment: {sentiment_dict['compound']:.3f}")
                    
                i += 1
                
            except Exception as e:
                print(f"❌ Error processing article: {e}")
                
            if i >= 50:
                print("🎯 Reached 50 articles limit")
                break
                
        # Calculate results
        if i > 0:
            avg_sentiment = sum_sentiment / i
            print(f"\n📊 Summary:")
            print(f"   Articles stored: {i}")
            print(f"   Unique articles: {len(seen_combinations)}")
            print(f"   Average sentiment: {avg_sentiment:.3f}")
            
            # Sentiment interpretation
            if avg_sentiment >= 0.05:
                sentiment_label = "Positive"
            elif avg_sentiment <= -0.05:
                sentiment_label = "Negative"
            else:
                sentiment_label = "Neutral"
            print(f"   Overall tone: {sentiment_label}")
            
        else:
            print("❌ No articles found for the given keywords")
            avg_sentiment = 0
            
    except Exception as e:
        print(f"❌ Query error: {e}")
        avg_sentiment = 0
    
    client.close()
    return avg_sentiment

if __name__ == "__main__":
    print("🌐 News Aggregator with OR Search")
    print("=" * 40)
    a = ["Trump", "Biden", "Election", "Economy", "Health"]
    result = store_news_with_user_keywords(a)
    if result is not None:
        print(f"\n🎯 Final average sentiment score: {result:.3f}")
    else:
        print("❌ Operation failed. Please check your inputs and try again.")