# US Visa Requirements Portal (pSEO)

A high-performance Programmatic SEO (pSEO) website designed to serve detailed US visa requirements (B1/B2, F1, H1B, J1, L1, O1) for citizens of all countries. The project features dynamic SEO optimization, structured data schemas, and automated AI-driven FAQ pipelines.

---

## 🛠️ Architecture & Tech Stack

- **Frontend**: [Astro](https://astro.build/) (Static Site Generation) custom-styled with Vanilla CSS.
- **Database**: [Supabase](https://supabase.com/) (PostgreSQL) storing visa records and generated FAQs.
- **Hosting**: [Vercel](https://vercel.com/) (Serverless Static Deployments).
- **Scraper**: Python (`BeautifulSoup4` & `requests`) for crawling travel.state.gov.
- **FAQ Generator**: Python + Llama 3.3 70B (NVIDIA NIM) + Google Autocomplete API for search intent harvesting and fact-checked FAQ generation.
- **Automation**: GitHub Actions scheduling monthly updates and triggering Vercel build/redeploy hooks.

---

## 📡 Programmatic Data & FAQ Pipeline

1. **Scraping**: `scrape_and_push.py` and `robust_api_scraper.py` populate Supabase with structured records of required documents, fees, processing times, and official links.
2. **Keyword Harvesting**: `generate_faqs.py` queries Google's autocomplete API for real-world search queries matching `[US visa type] requirements for [country] citizens`.
3. **LLM Generation**: Llama 3.3 70B synthesizes these search queries and official visa details into natural, SEO-rich FAQs.
4. **Frontend Delivery**: Astro maps every country/visa combination dynamically, serving interactive accordion questions and injecting structured `FAQPage` JSON-LD schemas.
