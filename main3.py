import os
import pandas as pd 
import asyncio
import logging
from dotenv import load_dotenv
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig, LLMConfig, CacheMode
import fireworks.client
from serpapi import GoogleSearch
import json
from crawl4ai.extraction_strategy import LLMExtractionStrategy
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
log_file = 'outreach_workflow.log'
# print(f"Setting up logging to: {os.path.abspath(log_file)}")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True  # Override any existing logging config
)
logger = logging.getLogger(__name__)

# Test logging immediately
# print("Testing logging setup...")
logger.info("=== LOGGING INITIALIZED ===")
# print(f"Log file exists: {os.path.exists(log_file)}")

# Define schema for company summary extraction
class CompanySummary(BaseModel):
    summary: str = Field(description="A concise 2-3 line summary of what the company does, who they are, and what they're looking for")

class OutreachGenerator:
    def __init__(self):
        print("  Initializing OutreachGenerator...")
        print("  Loading API keys...")
        self.fireworks_api_key = os.getenv("FIREWORKS_API_KEY")
        self.serpapi_key = os.getenv("SERPAPI_KEY")
        
        if not self.fireworks_api_key:
            raise ValueError("FIREWORKS_API_KEY not found in environment variables")
        print("  ✅ API keys loaded")
            
        print("  Setting up Fireworks client...")
        # Initialize clients
        fireworks.client.api_key = self.fireworks_api_key
        print("  ✅ Fireworks client configured")
        
        print("  Loading company cache...")
        # Cache management
        self.company_cache = self.load_company_cache()
        print(f"  ✅ Loaded {len(self.company_cache)} cached companies")
        
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



    def _apply_rate_limit(self) -> None:
        """Apply rate limiting between API calls"""
        current_time = time.time()
        time_since_last_call = current_time - self.last_api_call
        
        if time_since_last_call < self.min_delay:
            sleep_time = self.min_delay - time_since_last_call
            time.sleep(sleep_time)
        
        self.last_api_call = time.time()

    def get_prompt(self, resume: str, lead_title: str, company_name: str, 
                    company_info: str) -> str:
        """Generate improved prompt for the LLM focused on company info."""
        # Truncate resume to first 500 characters to save tokens
        resume_short = resume[:500] + "..." if len(resume) > 500 else resume
        
        prompt = f"""Create outreach asking about open opportunities at {company_name}.

MY SKILLS: {resume_short}
CONTACT: {lead_title}
COMPANY: {company_info}

Create:
1. LinkedIn request (<300 chars, ask about openings, reference company)
2. Cold email with this exact structure:
   - 2-3 lines of pleasantries and introduction
   - 3 achievements from my resume that match the company's business
   - "Looking forward to hearing from you, attaching my resume for your reference./ ask for an short 15 min call"

Return ONLY valid JSON:
{{
    "linkedin_request": "your linkedin message here",
    "email_subject": "your email subject here", 
    "email_body": "your email body here"
}}"""
        return prompt

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
                provider="fireworks_ai/accounts/fireworks/models/deepseek-v3", 
                api_token=self.fireworks_api_key
            ),
            extraction_type="schema",
            schema=CompanySummary.model_json_schema(),
            instruction="Extract a concise 2-3 line company summary focusing on: what they do, their industry, and their focus.",
            chunk_token_threshold=2000,
            overlap_rate=0.0,
            apply_chunking=False,
            input_format="markdown",
            extra_args={"temperature": 0.1, "max_tokens": 150},
        )
        
        config = CrawlerRunConfig(
            extraction_strategy=llm_strategy,
            cache_mode=CacheMode.BYPASS,
            remove_overlay_elements=True,
            remove_forms=True,
            only_text=True,  # Focus on text content only
            exclude_external_links=True,  # Remove external navigation
            exclude_social_media_links=True,  # Remove social media buttons
        )#
        
        async with AsyncWebCrawler(config=BrowserConfig(headless=True,verbose=True)) as crawler:
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
                model="accounts/fireworks/models/deepseek-v3",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.1,
            )
            
            generated_text = response.choices[0].message.content
            print("summary is: ", generated_text)
            return self._parse_generated_content(generated_text)
            
        except Exception as e:
            logger.error(f"Error generating content: {e}")
            raise

    def _extract_json_from_markdown(self, text: str) -> str:
        """Extract JSON content from markdown code blocks."""
        try:
            # Try to extract JSON from ```json code blocks
            json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if json_match:
                return json_match.group(1).strip()
            
            # Fallback: try to extract from any ``` code blocks
            code_match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
            if code_match:
                return code_match.group(1).strip()
            
            # If no code blocks found, return the original text
            return text.strip()
            
        except Exception as e:
            logger.warning(f"Error extracting JSON from markdown: {e}")
            return text.strip()

    def _parse_generated_content(self, generated_text: str) -> tuple[str, str]:
        """Parse JSON generated content to extract LinkedIn request and email."""
        try:
            # First extract JSON from markdown code blocks
            json_text = self._extract_json_from_markdown(generated_text)
            
            # Parse JSON response
            data = json.loads(json_text)
            
            linkedin_request = data.get("linkedin_request", "Failed to parse LinkedIn request")
            email_subject = data.get("email_subject", "")
            email_body = data.get("email_body", "")
            
            # Combine subject and body
            email_full = f"Subject: {email_subject}\n\n{email_body}" if email_subject else email_body
            
            
            return linkedin_request, email_full
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON response: {e}")
            logger.debug(f"Attempted to parse: {json_text[:200]}...")
            return "Failed to parse JSON response", "Failed to parse JSON response"
        except Exception as e:
            logger.error(f"Error parsing generated content: {e}")
            return "Failed to parse LinkedIn request", "Failed to parse email"


    async def process_row(self, index: int, row: pd.Series, resume_content: str) -> Dict[str, str]:
        """Process a single row with comprehensive error handling."""
        try:
            logger.info(f"Processing row {index}: {row.get('First Name', '')} {row.get('Last Name', '')}")
            
            # Extract data
            company_website = row.get("Website", "")
            company_name = row.get("Company Name", "")
            
            # Skip person information gathering to save API costs
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
            
            # Check if we have company content
            if not company_info.strip():
                logger.warning(f"Row {index}: No company info available, skipping LLM generation")
                return {"LinkedIn Request": "No company info available", "Cold Email": "No company info available"}
            
            # Generate content
            prompt = self.get_prompt(
                resume=resume_content,
                lead_title=row.get("Lead Title", ""),
                company_name=company_name,
                company_info=company_info
            )
            
            linkedin_request, email_full = self.generate_content(prompt)
            print(linkedin_request)
            print(email_full)
            logger.info(f"✅ Successfully processed row {index}")
            return {"LinkedIn Request": linkedin_request, "Cold Email": email_full}
            
        except Exception as e:
            logger.error(f"Error processing row {index}: {e}")
            return {"LinkedIn Request": f"Error: {str(e)}", "Cold Email": f"Error: {str(e)}"}

    async def process_excel_file(self, input_file: str, resume_file: str, output_file: str = None) -> None:
        """Main processing function with improved error handling and progress tracking."""
        print("  Starting Excel file processing...")
        if output_file is None:
            output_file = f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        print(f"  Output will be saved to: {output_file}")
        
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
    print("=== STARTING COLD EMAIL GENERATOR ===")
    logger.info("Application starting...")
    
    # Configuration - Make these configurable
    INPUT_FILE = "S:/Portfolio/ColdEmailGenerator/Companies_Hiring_Tech_Roles.xlsx"
    RESUME_FILE = "S:/Portfolio/ColdEmailGenerator/Resumeforcoldemail.txt"
    OUTPUT_FILE = "enhanced_output.xlsx"
    
    print(f"Input file: {INPUT_FILE}")
    print(f"Resume file: {RESUME_FILE}")
    print(f"Output file: {OUTPUT_FILE}")
    
    try:
        print("Checking if files exist...")
        if not os.path.exists(INPUT_FILE):
            raise FileNotFoundError(f"Input file not found: {INPUT_FILE}")
        if not os.path.exists(RESUME_FILE):
            raise FileNotFoundError(f"Resume file not found: {RESUME_FILE}")
        print("✅ All input files found")
        
        # print("Initializing OutreachGenerator...")
        # Initialize the generator
        generator = OutreachGenerator()
        print("✅ OutreachGenerator initialized")
        
        print("Starting file processing...")
        # Process the files
        await generator.process_excel_file(INPUT_FILE, RESUME_FILE, OUTPUT_FILE)
        print("✅ Processing completed successfully!")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        logger.error(f"Application failed: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    asyncio.run(main())