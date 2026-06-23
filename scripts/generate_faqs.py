import os
import time
import json
import requests
import urllib.parse
from bs4 import BeautifulSoup
from supabase import create_client, Client
from openai import OpenAI

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None
    print("WARNING: Supabase credentials not found. Running in dry-run mode.")

if NVIDIA_API_KEY:
    ai_client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=NVIDIA_API_KEY
    )
else:
    ai_client = None
    print("WARNING: NVIDIA API Key not found. Running in dry-run mode.")

# Friendly names of visa slugs for google autocomplete search
VISA_SEARCH_NAMES = {
    "b1-b2-tourist-visa": "tourist visa",
    "f1-student-visa": "student visa",
    "h1b-work-visa": "H1B work visa",
    "j1-exchange-visitor-visa": "J1 exchange visitor visa",
    "l1-intracompany-transfer-visa": "L1 transfer visa",
    "o1-extraordinary-ability-visa": "O1 extraordinary ability visa",
}

# Fallback question templates if autocomplete suggests nothing relevant
FALLBACK_QUESTIONS = {
    "b1-b2-tourist-visa": [
        "What is the processing time for a US B1/B2 tourist visa for {country} citizens?",
        "What are the required documents for a US B1/B2 visa from {country}?",
        "How long is a US tourist visa valid for citizens of {country}?",
        "How much is the US B1/B2 visa fee for {country} applicants?"
    ],
    "f1-student-visa": [
        "How can a student from {country} apply for a US F1 visa?",
        "What documents are required for an F1 visa interview from {country}?",
        "What is the fee and validity of a US F1 student visa for {country}?",
        "How long does it take to process a US student visa in {country}?"
    ],
    "h1b-work-visa": [
        "What is the validity period of an H1B work visa for {country} citizens?",
        "What are the document requirements for {country} applicants seeking an H1B visa?",
        "How much is the H1B visa fee for citizens of {country}?",
        "Where must a citizen of {country} go to apply for their US H1B work visa?"
    ],
    "j1-exchange-visitor-visa": [
        "What documents does a {country} citizen need for a US J1 exchange visitor visa?",
        "How long is a J1 visa valid for citizens of {country}?",
        "What is the application fee for a J1 visa in {country}?",
        "How long does J1 visa processing take for {country} applicants?"
    ],
    "l1-intracompany-transfer-visa": [
        "What is the validity of an L1 intracompany transfer visa for {country} citizens?",
        "What documents are required for an L1 visa interview in {country}?",
        "How much is the L1 visa fee for citizens of {country}?",
        "What is the processing time for L1 visa applications from {country}?"
    ],
    "o1-extraordinary-ability-visa": [
        "How does a citizen of {country} qualify for a US O1 extraordinary ability visa?",
        "What documents must {country} applicants submit for an O1 visa?",
        "What is the fee and validity of an O1 visa for {country} citizens?",
        "How long does O1 visa processing take for citizens of {country}?"
    ],
}


# ─────────────────────────────────────────────
# 1. GET GOOGLE COMPLETE SUGGESTIONS (Deterministic Keyword Sourcing)
# ─────────────────────────────────────────────
def get_google_suggestions(query: str) -> list:
    """Queries the Google Suggest API to pull live autocomplete terms."""
    url = f"http://suggestqueries.google.com/complete/search?client=chrome&q={urllib.parse.quote(query)}"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data[1]  # List of string queries
    except Exception as e:
        print(f"  Google Suggest API error: {e}")
    return []


def harvest_real_keywords(country_name: str, visa_slug: str) -> list:
    """Builds search terms and fetches actual autocompletes from Google."""
    search_name = VISA_SEARCH_NAMES.get(visa_slug, "visa")
    queries = [
        f"us {search_name} for {country_name}",
        f"how to get us {search_name} from {country_name}"
    ]
    
    keywords = []
    for q in queries:
        suggestions = get_google_suggestions(q)
        keywords.extend(suggestions)
        time.sleep(0.5)  # Be polite to Google Suggest
        
    # Deduplicate and limit to top 8 suggestions
    seen = set()
    cleaned = []
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower not in seen:
            seen.add(kw_lower)
            cleaned.append(kw)
            
    return cleaned[:8]


# ─────────────────────────────────────────────
# 2. GENERATE FAQS USING LLM
# ─────────────────────────────────────────────
def generate_faqs_for_row(row: dict) -> list:
    """Takes a row's current factual columns, harvests Google keywords, and calls LLM to generate FAQs."""
    country = row["country_name"]
    visa_type = row["visa_type"]
    visa_slug = row["visa_slug"]
    
    # Harvest live google search keywords
    keywords = harvest_real_keywords(country, visa_slug)
    print(f"  Harvested keywords: {keywords}")
    
    # Prepare factual constraints
    fee = row.get("fee_usd", 185)
    validity = row.get("validity", "Varies")
    processing = row.get("processing_time", "Varies")
    docs = row.get("required_documents", [])
    notes = row.get("notes", "")
    
    facts_str = f"""
Facts about {visa_type} for {country} citizens:
- Official visa application fee: ${fee} USD
- Visa validity period: {validity}
- Typical processing time: {processing}
- Required Documents: {', '.join(docs)}
- Notes: {notes}
"""

    fallback_questions = FALLBACK_QUESTIONS.get(visa_slug, [])
    fallback_questions_str = "\n".join([f"- {q.format(country=country)}" for q in fallback_questions])

    prompt = f"""
You are an expert, legally precise US immigration assistant. Your task is to output exactly 4 Frequently Asked Questions (FAQs) with answers about the US {visa_type} for citizens of {country}.

{facts_str}

Use these source keywords to formulate the questions:
{keywords}

Instructions for Questions:
1. Formulate 4 natural questions representing what searchers are looking for. If the harvested keywords are sparse or not questions, convert them into clear questions.
2. Ensure questions are professionally phrased. Always refer to citizens as "citizens of {country}" or "applicants from {country}". Never use phrasing like "{country} citizens" or "{country} applicants" (e.g., use "citizens of Brazil" instead of "Brazil citizens" or "Brazilian citizens").
3. If keywords are missing or irrelevant, use or adapt the following pre-approved questions:
{fallback_questions_str}

Instructions for Answers:
1. Answer all questions facts-only, based STRICTLY on the facts provided above. Do NOT invent or hallucinate any rules, fees, dates, or documents.
2. Elaborate on the answers to make them complete, detailed, and SEO-rich (write 2 to 3 comprehensive sentences). Avoid simple one-word or short fragment answers. For example, explain what the fee is for, what the validity period means, or how processing times work, strictly using the facts.
3. Keep the tone professional, authoritative, and helpful.

Output your response ONLY as a valid JSON array of objects. Do not include markdown code block formatting (like ```json). Just start with [ and end with ].

Expected JSON output format:
[
  {{
    "question": "Question text here?",
    "answer": "Factual, detailed answer text here (2-3 sentences)."
  }},
  ... (exactly 4 items)
]
"""

    if not ai_client:
        # Dry-run placeholder
        return [
            {"question": f"What is the fee for a US {visa_type} from {country}?", "answer": f"The fee is ${fee} USD."},
            {"question": f"How long is a US {visa_type} valid for {country}?", "answer": f"It is valid for {validity}."}
        ]

    try:
        response = ai_client.chat.completions.create(
            model="meta/llama-3.3-70b-instruct",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,  # Zero creativity, stick to the facts
            max_tokens=800,
            timeout=30.0,
        )
        
        content = response.choices[0].message.content.strip()
        # Clean potential markdown output formatting if model returned it anyway
        if content.startswith("```json"):
            content = content.replace("```json", "", 1)
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        faqs = json.loads(content)
        if isinstance(faqs, list) and len(faqs) > 0:
            return faqs
        else:
            raise ValueError("LLM returned invalid format")
            
    except Exception as e:
        print(f"  AI generation failed: {e}. Using templates instead.")
        # Programmatic local fallback to ensure we never push empty JSON or fail
        local_faqs = []
        for q_temp in fallback_questions[:4]:
            q = q_temp.format(country=country)
            # Answer builder based on simple rules to avoid calling LLM again
            if "fee" in q.lower():
                a = f"The official MRV application fee for a US {visa_type} is ${fee} USD for citizens of {country}. This fee must be paid online before scheduling the visa interview appointment and is non-refundable."
            elif "valid" in q.lower():
                a = f"A US {visa_type} is typically issued with a validity period of up to {validity} for citizens of {country}. The exact validity duration and whether it allows single or multiple entries are determined by the reciprocity agreement between the United States and {country}."
            elif "processing" in q.lower() or "time" in q.lower():
                a = f"The processing time for the US {visa_type} is approximately {processing} after the interview has been conducted. Applicants should plan ahead as consulate appointment wait times are not included in this timeline and vary by location."
            else:
                a = f"To apply for a US {visa_type}, citizens of {country} must present several required documents. These include a valid passport, a completed DS-160 confirmation page, and visa-specific supporting papers such as {', '.join(docs[:2])}."
            local_faqs.append({"question": q, "answer": a})
        return local_faqs


# ─────────────────────────────────────────────
# 3. DATABASE UPDATE LOGIC
# ─────────────────────────────────────────────
def push_faqs_to_supabase(country_slug: str, visa_slug: str, faqs: list) -> bool:
    """Pushes the FAQ json array to the specific database row."""
    if not supabase:
        print(f"  [DRY RUN] Would update: {country_slug}/{visa_slug} with {len(faqs)} FAQs")
        return True
        
    try:
        supabase.table("visa_requirements").update({"faqs": faqs}).eq(
            "country_slug", country_slug
        ).eq("visa_slug", visa_slug).execute()
        print(f"  ✓ Successfully updated FAQs for {country_slug}/{visa_slug}")
        return True
    except Exception as e:
        print(f"  Database push error for {country_slug}/{visa_slug}: {e}")
        return False


# ─────────────────────────────────────────────
# 4. MAIN BATCH CONTROLLER
# ─────────────────────────────────────────────
def run_faq_pipeline(limit=600):
    """Fetches rows with NULL faqs, processes them up to the limit, with a 2-second rate-limiting delay."""
    if not supabase:
        print("ERROR: Supabase connection is required to fetch target rows.")
        return
        
    print(f"Fetching rows where faqs is NULL (Limit: {limit})...")
    
    # Query only rows where 'faqs' column is null or doesn't exist
    result = supabase.table("visa_requirements").select(
        "country_name, country_slug, visa_type, visa_slug, fee_usd, validity, processing_time, required_documents, notes"
    ).is_("faqs", "null").limit(limit).execute()
    
    rows = result.data
    total_found = len(rows)
    print(f"Found {total_found} rows that need FAQ generation.\n")
    
    if total_found == 0:
        print("No pages need FAQs updated. We are fully complete!")
        return

    for i, row in enumerate(rows):
        print(f"[{i+1}/{total_found}] Processing: {row['country_name']} / {row['visa_slug']}")
        
        faqs = generate_faqs_for_row(row)
        push_faqs_to_supabase(row["country_slug"], row["visa_slug"], faqs)
        
        # Polite 2-second delay to guarantee we stay safely below 40 RPM limit of NIM API
        time.sleep(2.0)
        
    print("\n✓ Batch generation complete!")


if __name__ == "__main__":
    # Run the database update pipeline (updates up to 600 rows per run)
    run_faq_pipeline(limit=600)
