# Cold Email Generator

An automated system for generating personalized LinkedIn connection requests and cold emails using AI. The system scrapes company information from websites, searches for professional information, and uses LLM to create customized outreach content.

## Features

- 🚀 **Automated Content Generation**: AI-powered LinkedIn requests and cold emails
- 🏢 **Company Information Scraping**: Extracts company summaries from websites
- 👥 **Professional Research**: Gathers person/company information via search APIs
- 💾 **Smart Caching**: Avoids re-scraping already processed companies
- 📊 **Excel Integration**: Processes input/output via Excel files
- 🔄 **Retry Logic**: Robust error handling with automatic retries
- 📝 **Logging**: Comprehensive workflow logging

## Environment Setup

### 1. Prerequisites

- Python 3.8+
- Windows/macOS/Linux

### 2. Clone Repository

```bash
git clone <your-repo-url>
cd ColdEmailGenerator
```

### 3. Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

**Note**: After installing, run the following for Playwright browser setup:
```bash
playwright install
```

### 5. Environment Variables

Create a `.env` file in the project root:

```env
# Required for all versions
FIREWORKS_API_KEY=your_fireworks_api_key_here

# Required for main.py and main2.py (optional for main3.py)
SERPAPI_KEY=your_serpapi_key_here
```

## API Keys Setup

### Fireworks AI API Key
1. Visit [Fireworks AI](https://fireworks.ai/)
2. Sign up/login to your account
3. Navigate to API Keys section
4. Generate a new API key
5. Add to `.env` file as `FIREWORKS_API_KEY`

### SerpAPI Key (Google Search)
1. Visit [SerpAPI](https://serpapi.com/)
2. Sign up for a free account (100 free searches/month)
3. Get your API key from dashboard
4. Add to `.env` file as `SERPAPI_KEY`

## Input Files Required

1. **Excel File**: Company/contact data (`Companies_Hiring_Tech_Roles.xlsx`)
   - Required columns: `Company Name`, `Website`, `First Name`, `Last Name`, `Lead Title`
   - Optional columns: `Job Title`, `Lead Linkedin`

2. **Resume File**: Your resume content (`Resumeforcoldemail.txt`)
   - Plain text format
   - Include skills, experience, achievements

## Main Files Overview

### main.py - Initial version for testing purposes

### main2.py - Enhanced with Full Research
Comprehensive version with extensive error handling and professional research.

```
┌─────────────────────────────────────────────────────────────┐
│                       main2.py Workflow                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📊 Load Excel File ──► 📝 Load Resume                     │
│           │                     │                          │
│           └─────────────────────┘                          │
│                     │                                      │
│  🔄 For Each Contact:                                      │
│                     │                                      │
│  ┌─────────────────▼─────────────────┐                     │
│  │ 🔍 Comprehensive Person Research  │                     │
│  │    ├─ Google Search (SerpAPI)     │                     │
│  │    ├─ LinkedIn Profile Info       │                     │
│  │    └─ Professional Background     │                     │
│  └─────────────────┬─────────────────┘                     │
│                     │                                      │
│  ┌─────────────────▼─────────────────┐                     │
│  │ 🏢 Company Information            │                     │
│  │    ├─ Check Cache First           │                     │
│  │    ├─ Web Scraping (LLM)          │                     │
│  │    ├─ Retry Logic (3x)            │                     │
│  │    └─ Error Handling              │                     │
│  └─────────────────┬─────────────────┘                     │
│                     │                                      │
│  ┌─────────────────▼─────────────────┐                     │
│  │ 🤖 Advanced Content Generation    │                     │
│  │    ├─ Personalized Prompts        │                     │
│  │    ├─ Context-Aware Templates     │                     │
│  │    ├─ Rate Limiting               │                     │
│  │    └─ Content Validation          │                     │
│  └─────────────────┬─────────────────┘                     │
│                     │                                      │
│  💾 Save Progress ◄─┘ (Every 5 rows)                       │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ 🔧 Features: Full Research, Robust Error Handling          │
│ 💰 Cost: High (Person research + Company scraping + LLM)   │
│ 🎯 Best for: High-quality personalization, small batches   │
└─────────────────────────────────────────────────────────────┘
```

### main3.py - Streamlined Company-Only Version
Optimized version focusing on company information only to reduce API costs.

```
┌─────────────────────────────────────────────────────────────┐
│                       main3.py Workflow                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📊 Load Excel File ──► 📝 Load Resume                     │
│           │                     │                          │
│           └─────────────────────┘                          │
│                     │                                      │
│  🔄 For Each Contact:                                      │
│                     │                                      │
│  ┌─────────────────▼─────────────────┐                     │
│  │ 🏢 Company-Only Information       │                     │
│  │    ├─ Check Cache First           │                     │
│  │    ├─ Web Scraping (DeepSeek)     │                     │
│  │    ├─ Smart Content Filtering     │                     │
│  │    └─ Minimal Token Usage         │                     │
│  └─────────────────┬─────────────────┘                     │
│                     │                                      │
│  ┌─────────────────▼─────────────────┐                     │
│  │ 🤖 Efficient Content Generation   │                     │
│  │    ├─ Company-Focused Prompts     │                     │
│  │    ├─ JSON Response Format        │                     │
│  │    ├─ Rate Limiting (1s)          │                     │
│  │    └─ Error Recovery              │                     │
│  └─────────────────┬─────────────────┘                     │
│                     │                                      │
│  💾 Auto-Save ◄─────┘ (Progress tracking)                  │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ 🔧 Features: Cost-Optimized, Company Focus, Fast           │
│ 💰 Cost: Low (Company scraping + LLM only)                 │
│ 🎯 Best for: Large batches, budget-conscious processing    │
└─────────────────────────────────────────────────────────────┘
```

## Usage

### 1. Prepare Input Files
- Place your Excel file with contact data in the project directory
- Create/update your resume text file
- Update file paths in the chosen main script

### 2. Choose Your Version

**For comprehensive personalization:**
```bash
python main2.py
```

**For cost-effective processing:**
```bash
python main3.py
```

**For schema-based optimization:**
```bash
python main.py
```

### 3. Monitor Progress
- Watch console output for real-time progress
- Check `outreach_workflow.log` for detailed logging
- Intermediate results saved every 5 rows (main2.py, main3.py)

## Output

The scripts generate:

1. **Enhanced Excel File**: Original data + generated content
   - `LinkedIn Request` column: Personalized connection requests
   - `Cold Email` column: Complete emails with subjects
   - `Processing Status` and `Processed At` columns (main2.py, main3.py)

2. **Cache Files**: 
   - `company_cache.txt`: Stores scraped company information
   - `company_cache.backup.txt`: Backup of cache data

3. **Logs**:
   - `outreach_workflow.log`: Detailed processing logs

## Cost Optimization Tips

1. **Use main3.py** for large batches (company info only)
2. **Use main2.py** for small, high-value prospects (full research)
3. **Cache Management**: Never delete cache files to avoid re-scraping
4. **Batch Processing**: Process in smaller batches to manage costs
5. **API Rate Limits**: Built-in delays prevent hitting API limits

## Troubleshooting

### Common Issues

**Logging not working:**
- Check file permissions in project directory
- Ensure Python has write access to log files

**API Errors:**
- Verify API keys in `.env` file
- Check API quota/billing status
- Ensure stable internet connection

**Import Errors:**
- Confirm virtual environment is activated
- Run `pip install -r requirements.txt` again
- For Playwright: `playwright install`

**File Path Issues:**
- Use absolute paths in main functions
- Ensure input files exist and are accessible
- Check file format compatibility (Excel .xlsx)

## Security Notes

- Never commit `.env` files to version control
- Keep API keys secure and rotate regularly
- Review `.gitignore` to prevent data leakage
- Cache files may contain sensitive company information

## License

This project is for educational and personal use. Ensure compliance with:
- Website terms of service when scraping
- API usage policies
- Data privacy regulations
- Professional ethics in outreach

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review log files for detailed errors
3. Verify API key validity and quotas
4. Ensure all dependencies are correctly installed
