import os
import pandas as pd
import asyncio
import logging
from dotenv import load_dotenv
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig, LLMConfig, CacheMode
import fireworks.client
from serpapi import GoogleSearch
import json
from crawl4ai.extraction_strategy import LLMExtractionStrategy, JsonCssExtractionStrategy
from pydantic import BaseModel, Field
from pathlib import Path
import time
import backoff
from typing import Optional, Dict, List
from datetime import datetime
import re

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('outreach_workflow.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Define schema for company summary extraction
class CompanySummary(BaseModel):
    summary: str = Field(description="A concise 2-3 line summary of what the company does, who they are, and what they're looking for")

class OutreachGenerator:
    def __init__(self):
        self.fireworks_api_key = os.getenv("FIREWORKS_API_KEY")
        self.serpapi_key = os.getenv("SERPAPI_KEY")
            
        # Initialize clients
        fireworks.client.api_key = self.fireworks_api_key
        
        # Cache management
        self.company_cache = self.load_company_cache()
        
        # Rate limiting
        self.last_api_call = 0
        self.min_delay = 1.0  # Minimum delay between API calls
        
        logger.info(f"Initialized with {len(self.company_cache)} cached companies")

    # Caching methods with improved error handling
    def load_company_cache(self) -> Dict[str, str]:
        """Load company cache from file with error handling"""
        cache_file = "company_cache.txt"
        cache = {}
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        try:
                            if '|||' in line:
                                parts = line.strip().split('|||', 1)
                                if len(parts) == 2:
                                    company_name, summary = parts
                                    cache[company_name.strip()] = summary.strip()
                        except Exception as e:
                            logger.warning(f"Error parsing cache line {line_num}: {e}")
        except Exception as e:
            logger.error(f"Error loading company cache: {e}")
        return cache

    def save_company_cache(self) -> None:
        """Save company cache to file with backup"""
        cache_file = "company_cache.txt"
        backup_file = "company_cache.backup.txt"
        
        try:
            # Create backup of existing file
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as src:
                    with open(backup_file, 'w', encoding='utf-8') as dst:
                        dst.write(src.read())
            
            # Write new cache
            with open(cache_file, 'w', encoding='utf-8') as f:
                for company_name, summary in self.company_cache.items():
                    # Sanitize data to prevent parsing issues
                    clean_company = company_name.replace('|||', '').strip()
                    clean_summary = summary.replace('|||', '').strip()
                    f.write(f"{clean_company}|||{clean_summary}\n")
            logger.info(f"Saved {len(self.company_cache)} companies to cache")
        except Exception as e:
            logger.error(f"Error saving company cache: {e}")


    @backoff.on_exception(backoff.expo, Exception, max_tries=3, max_time=60)
    def get_person_info(self, query: str) -> str:
        """Get person information from Google search with retry logic."""
        if not query.strip():
            return "No query provided."
            
        try:
            # Rate limiting
            self._apply_rate_limit()
            
            search = GoogleSearch({
                "engine": "google",
                "api_key": self.serpapi_key,
                "q": f"{query}",  # firstname lastname company - broader search
                "num": 5
            })
            
            results_dict = search.get_dict()
            
            if 'organic_results' not in results_dict:
                logger.warning(f"No organic results found for LinkedIn search: {query}")
                return "No LinkedIn profile found."
            
            results = results_dict["organic_results"]
            person_info = []
            
            for result in results:
                title = result.get('title', '').strip()
                snippet = result.get('snippet', '').strip()
                if title and snippet:
                    person_info.append(f"{title}: {snippet}")
            
            if person_info:
                return "\n".join(person_info)
            else:
                logger.warning(f"No information found for: {query}")
                return "No information found."
                
        except Exception as e:
            logger.error(f"Error getting LinkedIn snippet for {query}: {e}")
            raise

    def _apply_rate_limit(self) -> None:
        """Apply rate limiting between API calls"""
        current_time = time.time()
        time_since_last_call = current_time - self.last_api_call
        
        if time_since_last_call < self.min_delay:
            sleep_time = self.min_delay - time_since_last_call
            time.sleep(sleep_time)
        
        self.last_api_call = time.time()

    def get_prompt(self, resume: str, lead_title: str, company_name: str, 
                   job_title: str, person_info: str, company_info: str) -> str:
        """Generate improved prompt for the LLM with better structure."""
        return f"""You are an expert at writing personalized, professional outreach messages.

MY BACKGROUND:
{resume}

TARGET OPPORTUNITY:
- Position: {job_title}
- Company: {company_name}
- Contact: {lead_title}

ABOUT THE RECIPIENT:
{person_info}

ABOUT THE COMPANY:
{company_info}

TASK: Create two pieces of outreach content that reference what the recipient is currently doing based on the research above:

1. A LinkedIn connection request that:
   - Is under 300 characters
   - References something specific from their profile/company
   - Mentions the role naturally
   - Sounds genuinely interested, not salesy

2. A cold email that:
   - Has a compelling, specific subject line
   - Opens with a genuine connection/reference
   - Briefly highlights 1-2 relevant qualifications
   - Shows knowledge of their company/role
   - Ends with a soft, specific call-to-action
   - Is 150-250 words total

FORMAT YOUR RESPONSE EXACTLY AS FOLLOWS:
LINKEDIN_REQUEST_START
[Your LinkedIn connection request here - max 300 chars]
LINKEDIN_REQUEST_END

EMAIL_START
Subject: [Compelling subject line]

[Email body - keep it concise and personalized]
EMAIL_END
"""

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    async def scrape_url(self, url: str) -> str:
        """Enhanced URL scraping with better error handling and validation."""
        if not self._is_valid_url(url):
            logger.warning(f"Invalid URL provided: {url}")
            return ""
            
        logger.info(f"Scraping URL: {url}")
        
        try:
            return await self._scrape_with_llm_strategy(url)
                
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return ""

    def _is_valid_url(self, url) -> bool:
        """Validate URL format"""
        if not url or not isinstance(url, str):
            return False
        return url.startswith(('http://', 'https://'))

    async def _scrape_with_llm_strategy(self, url: str) -> str:
        """Scrape using LLM strategy"""
        logger.info("Using LLM strategy ")
        
        llm_strategy = LLMExtractionStrategy(
            llm_config=LLMConfig(
                provider="fireworks_ai/accounts/fireworks/models/deepsek0-v3p1", 
                api_token=self.fireworks_api_key
            ),
            extraction_type="schema",
            schema=CompanySummary.model_json_schema(),
            instruction="Extract a concise 2-3 line company summary focusing on: what they do, their industry, and their scale/focus.",
            chunk_token_threshold=1000,
            overlap_rate=0.1,
            apply_chunking=False,
            input_format="markdown",
            extra_args={"temperature": 0.1, "max_tokens": 200},
        )
        
        config = CrawlerRunConfig(
            extraction_strategy=llm_strategy,
            cache_mode=CacheMode.BYPASS,
            remove_overlay_elements=True,
            remove_forms=True,
            only_text=True,  # Focus on text content only
            exclude_external_links=True,  # Remove external navigation
            exclude_social_media_links=True,  # Remove social media buttons
            page_timeout=30000,  # 30 seconds timeout
            delay_before_return_html=2000  # Wait 2 seconds for page load
        )
        
        async with AsyncWebCrawler(config=BrowserConfig(headless=False)) as crawler:
            result = await crawler.arun(url=url, config=config)
            
            if result.success and result.extracted_content:
                # LLM extraction only - works across all website types
                
                # Return extracted content
                return self._parse_extraction_result(result.extracted_content)
            else:
                logger.warning(f"LLM extraction failed for {url}")
                return ""


    def _parse_extraction_result(self, extracted_content: str) -> str:
        """Parse extraction result to get summary"""
        try:
            content_data = json.loads(extracted_content)
            
            if isinstance(content_data, dict) and "summary" in content_data:
                return content_data["summary"]
            elif isinstance(content_data, list) and content_data:
                if isinstance(content_data[0], dict) and "summary" in content_data[0]:
                    return content_data[0]["summary"]
            
            logger.warning("No summary found in extraction result")
            return "No summary extracted"
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse extraction result: {e}")
            return "Failed to parse extraction result"

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    def generate_content(self, prompt: str) -> tuple[str, str]:
        """Generate LinkedIn request and email content with retry logic."""
        try:
            self._apply_rate_limit()
            
            response = fireworks.client.ChatCompletion.create(
                model="accounts/fireworks/models/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.1,
            )
            
            generated_text = response.choices[0].message.content
            return self._parse_generated_content(generated_text)
            
        except Exception as e:
            logger.error(f"Error generating content: {e}")
            raise

    def _parse_generated_content(self, generated_text: str) -> tuple[str, str]:
        """Parse generated content to extract LinkedIn request and email."""
        try:
            # Extract LinkedIn request
            linkedin_match = re.search(
                r'LINKEDIN_REQUEST_START\s*(.*?)\s*LINKEDIN_REQUEST_END', 
                generated_text, 
                re.DOTALL
            )
            linkedin_request = linkedin_match.group(1).strip() if linkedin_match else "Failed to parse LinkedIn request"
            
            # Extract email
            email_match = re.search(
                r'EMAIL_START\s*(.*?)\s*EMAIL_END', 
                generated_text, 
                re.DOTALL
            )
            email_full = email_match.group(1).strip() if email_match else "Failed to parse email"
            
            # Validate LinkedIn request length
            if len(linkedin_request) > 300:
                logger.warning(f"LinkedIn request too long ({len(linkedin_request)} chars), truncating")
                linkedin_request = linkedin_request[:297] + "..."
            
            return linkedin_request, email_full
            
        except Exception as e:
            logger.error(f"Error parsing generated content: {e}")
            return "Failed to parse LinkedIn request", "Failed to parse email"

    def _extract_linkedin_id(self, linkedin_url: str) -> str:
        """Extract LinkedIn ID from URL with validation."""
        
        if "/in/" in linkedin_url:
            linkedin_id = linkedin_url.split("/in/")[-1].rstrip('/')
            # Clean up any trailing parameters
            linkedin_id = linkedin_id.split('?')[0].split('/')[0]
            return linkedin_id
        
        return ""

    async def process_row(self, index: int, row: pd.Series, resume_content: str) -> Dict[str, str]:
        """Process a single row with comprehensive error handling."""
        try:
            logger.info(f"Processing row {index}: {row.get('First Name', '')} {row.get('Last Name', '')}")
            
            # Extract data
            lead_linkedin = row.get("Lead Linkedin", "")
            company_website = row.get("Website", "")
            company_name = row.get("Company Name", "")
            
            # Get person information via Google search
            first_name = row.get("First Name", "").strip()
            last_name = row.get("Last Name", "").strip()
            if first_name and last_name:
                search_query = f"{first_name} {last_name} {company_name}"
                lead_info = self.get_person_info(search_query)
            else:
                logger.warning(f"Row {index}: Missing first/last name")
                lead_info = ""
            
            # Get company information (with caching)
            if company_name in self.company_cache:
                logger.info(f"Using cached info for {company_name}")
                company_info = self.company_cache[company_name]
            else:
                if company_website:
                    logger.info(f"Scraping new company: {company_name}")
                    company_info = await self.scrape_url(company_website)
                    if company_info and company_info != "No summary extracted":
                        self.company_cache[company_name] = company_info
                        self.save_company_cache()
                else:
                    logger.warning(f"Row {index}: No company website provided")
                    company_info = ""
            
            # Check if we have enough content
            if not lead_info.strip() and not company_info.strip():
                logger.warning(f"Row {index}: No content scraped, skipping LLM generation")
                return {"LinkedIn Request": "No content available", "Cold Email": "No content available"}
            
            # Generate content
            prompt = self.get_prompt(
                resume=resume_content,
                lead_title=row.get("Lead Title", ""),
                company_name=company_name,
                job_title=row.get("Job Title", ""),
                person_info=lead_info,
                company_info=company_info
            )
            
            linkedin_request, email_full = self.generate_content(prompt)
            
            logger.info(f"✅ Successfully processed row {index}")
            return {"LinkedIn Request": linkedin_request, "Cold Email": email_full}
            
        except Exception as e:
            logger.error(f"Error processing row {index}: {e}")
            return {"LinkedIn Request": f"Error: {str(e)}", "Cold Email": f"Error: {str(e)}"}

    async def process_excel_file(self, input_file: str, resume_file: str, output_file: str = None) -> None:
        """Main processing function with improved error handling and progress tracking."""
        if output_file is None:
            output_file = f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        try:
            # Load input files
            logger.info(f"Loading input files...")
            df = pd.read_excel(input_file)
            logger.info(f"Loaded {len(df)} rows from Excel file")
            
            with open(resume_file, "r", encoding='utf-8') as f:
                resume_content = f.read()
            logger.info("Resume loaded successfully")
            
            # Validate DataFrame columns
            required_columns = ["Company Name"]

            
            # Add new columns for generated content
            df["LinkedIn Request"] = ""
            df["Cold Email"] = ""
            df["Processing Status"] = ""
            df["Processed At"] = ""
            
            # Process each row
            successful_rows = 0
            failed_rows = 0
            
            for index, row in df.iterrows():
                try:
                    result = await self.process_row(index, row, resume_content)
                    
                    # Update DataFrame
                    df.at[index, "LinkedIn Request"] = result["LinkedIn Request"]
                    df.at[index, "Cold Email"] = result["Cold Email"]
                    df.at[index, "Processing Status"] = "Success" if not result["LinkedIn Request"].startswith("Error") else "Failed"
                    df.at[index, "Processed At"] = datetime.now().isoformat()
                    
                    if result["LinkedIn Request"].startswith("Error"):
                        failed_rows += 1
                    else:
                        successful_rows += 1
                    
                    # Save progress periodically
                    if (index + 1) % 5 == 0:
                        df.to_excel(output_file, index=False)
                        logger.info(f"Progress saved: {index + 1}/{len(df)} rows processed")
                    
                    # Rate limiting between rows
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Fatal error processing row {index}: {e}")
                    df.at[index, "Processing Status"] = f"Fatal Error: {str(e)}"
                    df.at[index, "Processed At"] = datetime.now().isoformat()
                    failed_rows += 1
            
            # Final save
            df.to_excel(output_file, index=False)
            self.save_company_cache()  # Final cache save
            
            # Summary
            logger.info(f"""
            Processing complete! 
            - Total rows: {len(df)}
            - Successful: {successful_rows}
            - Failed: {failed_rows}
            - Output saved to: {output_file}
            - Company cache: {len(self.company_cache)} companies
            """)
            
        except Exception as e:
            logger.error(f"Fatal error in main processing: {e}")
            raise

async def main():
    """Main function with configuration and error handling."""
    # Configuration - Make these configurable
    INPUT_FILE = "S:/Portfolio/ColdEmailGenerator/Companies_Hiring_Tech_Roles.xlsx"
    RESUME_FILE = "S:/Portfolio/ColdEmailGenerator/Resumeforcoldemail.txt"
    OUTPUT_FILE = "enhanced_output.xlsx"
    
    try:
        # Initialize the generator
        generator = OutreachGenerator()
        
        # Process the files
        await generator.process_excel_file(INPUT_FILE, RESUME_FILE, OUTPUT_FILE)
        
    except Exception as e:
        logger.error(f"Application failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())