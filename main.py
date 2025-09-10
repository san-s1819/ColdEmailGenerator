import os
import pandas as pd
import asyncio
from dotenv import load_dotenv
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig, LLMConfig, CacheMode
import h
from serpapi import GoogleSearch
import json
from crawl4ai.extraction_strategy import LLMExtractionStrategy, JsonCssExtractionStrategy
from pydantic import BaseModel, Field
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

# Define schema for company summary extraction
class CompanySummary(BaseModel):
    summary: str = Field(description="A concise 2-3 line summary of what the company does, who they are, and what they're looking for")

# Company caching functions
def load_company_cache():
    """Load company cache from file"""
    cache_file = "company_cache.txt"
    cache = {}
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            for line in f:
                if '|||' in line:
                    company_name, summary = line.strip().split('|||', 1)
                    cache[company_name] = summary
    return cache

def save_company_cache(cache):
    """Save company cache to file"""
    cache_file = "company_cache.txt"
    with open(cache_file, 'w', encoding='utf-8') as f:
        for company_name, summary in cache.items():
            f.write(f"{company_name}|||{summary}\n")

# Schema caching functions
def load_extraction_schema():
    """Load extraction schema from file"""
    schema_file = "extraction_schema.json"
    if os.path.exists(schema_file):
        with open(schema_file, 'r') as f:
            return json.load(f)
    return None

def save_extraction_schema(schema):
    """Save extraction schema to file"""
    schema_file = "extraction_schema.json"
    with open(schema_file, 'w') as f:
        json.dump(schema, f, indent=2)

serpapi_params = {
    "engine": "google",
    "api_key": os.getenv("SERPAPI_KEY")
}


def get_linkedin_snippet(query: str):
   """Get LinkedIn profile snippet from SERP API search results."""
   search = GoogleSearch({
       **serpapi_params,
       "q": f"site:linkedin.com/in {query}",
       "num": 3
   })
   results_dict = search.get_dict()
   if 'organic_results' in results_dict:
       results = results_dict["organic_results"]
   else:
       return "No LinkedIn profile found."
   
   # Extract relevant snippets from LinkedIn results
   linkedin_info = []
   for result in results:
       if 'linkedin.com/in' in result.get('link', ''):
           title = result.get('title', '')
           snippet = result.get('snippet', '')
           linkedin_info.append(f"{title}: {snippet}")
   
   return "\n".join(linkedin_info) if linkedin_info else "No LinkedIn information found."


# Get API keys from environment
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")
#SERP_API_KEY = os.getenv("SERP_API_KEY") # This will be used later

# Initialize Fireworks AI client
fireworks.client.api_key = os.getenv("FIREWORKS_API_KEY")

def get_prompt(resume, lead_title, company_name, job_title, scraped_content):
    """Generates the prompt for the LLM."""
    return f"""
My resume is:
---
{resume}
---

I am applying for the {job_title} position at {company_name}.
The hiring manager is the {lead_title}.

Here is some information I found about the company and the hiring manager:
---
{scraped_content}
---

Based on all this information, please generate:
1. A personalized and concise LinkedIn connection request (max 300 characters).
2. A personalized and compelling cold email to the hiring manager.

Format the output as follows:
LINKEDIN_REQUEST_START
[Your generated LinkedIn connection request here]
LINKEDIN_REQUEST_END

EMAIL_START
Subject: [Your generated email subject here]
[Your generated email body here]
EMAIL_END
"""

async def scrape_url(url):
    """Scrapes the content of a single URL using schema-based extraction."""
    if not url or not isinstance(url, str) or not url.startswith('http'):
        print(f"Skipping invalid URL: {url}")
        return ""
    print(f"Scraping URL: {url}")
    
    try:
        # Load existing schema or generate new one
        extraction_schema = load_extraction_schema()
        
        if extraction_schema is None:
            print("No cached schema found. Generating new schema (one-time LLM cost)...")
            # Generate schema using LLM (one-time cost)
            llm_strategy = LLMExtractionStrategy(
                llm_config=LLMConfig(provider="fireworks_ai/accounts/fireworks/models/gpt-oss-120b", api_token=FIREWORKS_API_KEY),
                extraction_type="schema",
                schema=CompanySummary.model_json_schema(),
                instruction="Based on the company website content, extract a concise 2-3 line summary - what they do, who they are.",
                chunk_token_threshold=1000,
                overlap_rate=0.1,
                apply_chunking=False,
                input_format="markdown",
                extra_args={"temperature": 0.1, "max_tokens": 200},
            )
            
            config = CrawlerRunConfig(
                extraction_strategy=llm_strategy,
                cache_mode=CacheMode.BYPASS,  # Smart content filtering
                remove_overlay_elements=True,
                remove_forms=True,
                only_text=True
            )
            
            async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as crawler:
                result = await crawler.arun(url=url, config=config)
                if result.success and result.extracted_content:
                    # Generate CSS schema for future use
                    css_schema = 
                    .generate_css_schema(
                        html=result.page_content,
                        schema=CompanySummary.model_json_schema(),
                        llm_config=LLMConfig(provider="fireworks_ai/accounts/fireworks/models/gpt-oss-120b", api_token=FIREWORKS_API_KEY)
                    )
                    save_extraction_schema(css_schema)
                    print("✅ Schema generated and cached for future use!")
                    
                    # Return current result
                    content_data = json.loads(result.extracted_content)
                    if isinstance(content_data, dict) and "summary" in content_data:
                        return content_data["summary"]
                    return "No summary extracted"
                else:
                    print(f"Failed to generate schema from {url}")
                    return ""
        else:
            print("Using cached CSS schema (FREE extraction)...")
            # Use cached CSS schema (FREE!)
            css_strategy = JsonCssExtractionStrategy(extraction_schema, verbose=True)
            
            config = CrawlerRunConfig(
                extraction_strategy=css_strategy,
                cache_mode=CacheMode.BYPASS,
                remove_overlay_elements=True,
                remove_forms=True,
                only_text=True
            )
            
            async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as crawler:
                result = await crawler.arun(url=url, config=config)
                if result.success and result.extracted_content:
                    content_data = json.loads(result.extracted_content)
                    print(f"✅ FREE extraction from {url}")
                    if isinstance(content_data, dict) and "summary" in content_data:
                        return content_data["summary"]
                    elif isinstance(content_data, list) and content_data:
                        if isinstance(content_data[0], dict) and "summary" in content_data[0]:
                            return content_data[0]["summary"]
                    return "No summary extracted"
                else:
                    print(f"CSS extraction failed for {url}")
                    return ""
                    
    except Exception as e:
        print(f"An error occurred while scraping {url}: {e}")
        return ""


async def main():
    # Configurable paths
    INPUT_FILE = "S:/Portfolio/ColdEmailGenerator/Companies_Hiring_Tech_Roles.xlsx"  # Replace with your actual Excel file path
    RESUME_FILE = "S:/Portfolio/ColdEmailGenerator/Resumeforcoldemail.txt"  # Replace with your actual resume file path

    # 1. Read input files
    try:
        df = pd.read_excel(INPUT_FILE)
        df.describe()
        with open(RESUME_FILE, "r") as f:
            resume_content = f.read()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    # Load company cache
    company_cache = load_company_cache()
    print(f"Loaded {len(company_cache)} companies from cache")

    # Add new columns for generated content
    df["LinkedIn Request"] = ""
    df["Cold Email"] = ""

    # 2. Process each row
    for index, row in df.iterrows():
        lead_linkedin = row.get("Lead Linkedin")
        company_website = row.get("Website")
        company_name = row.get("Company Name")

        # Extract LinkedIn ID
        linkedin_id = lead_linkedin.split("/in/")[-1] if "/in/" in lead_linkedin else ""

        # 3. Get LinkedIn snippet (no crawling)
        lead_info = get_linkedin_snippet(f"{linkedin_id} {company_name}") if linkedin_id else ""
        print("Lead info is", lead_info)

        # 4. Get company info (with caching)
        if company_name in company_cache:
            print(f"Using cached info for {company_name}")
            company_info = company_cache[company_name]
        else:
            print(f"Scraping new company: {company_name}")
            company_info = await scrape_url(company_website)
            if company_info and company_info != "No summary extracted":
                company_cache[company_name] = company_info
                save_company_cache(company_cache)  # Save immediately
        
        print("Company info is", company_info)
        combined_scraped_text = "\n".join(filter(None, [lead_info, company_info]))
        print("Combined scraped text is", combined_scraped_text)

        if not combined_scraped_text:
            print(f"No content scraped for row {index}. Skipping LLM generation.")
            continue

        # 4. Generate content with LLM
        prompt = get_prompt(
            resume=resume_content,
            lead_title=row.get("Lead Title"),
            company_name=row.get("Company Name"),
            job_title=row.get("Job Title"),
            scraped_content=combined_scraped_text
        )

        try:
            print(f"Generating content for {row.get('First Name')} {row.get('Last Name')}...")
            response = fireworks.client.ChatCompletion.create(
                model="accounts/fireworks/models/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.7,
            )
            generated_text = response.choices[0].message.content

            # 5. Parse the generated text
            linkedin_request = generated_text.split("LINKEDIN_REQUEST_START")[1].split("LINKEDIN_REQUEST_END")[0].strip()
            email_full = generated_text.split("EMAIL_START")[1].split("EMAIL_END")[0].strip()

            df.at[index, "LinkedIn Request"] = linkedin_request
            df.at[index, "Cold Email"] = email_full
            print(f"Successfully generated content for row {index}.")

        except Exception as e:
            print(f"Error generating content for row {index}: {e}")

    # 6. Save output and cache
    df.to_excel("output.xlsx", index=False)
    save_company_cache(company_cache)  # Final cache save
    print("Processing complete. Output saved to output.xlsx")
    print(f"Company cache updated with {len(company_cache)} companies")

if __name__ == "__main__":
    asyncio.run(main())
