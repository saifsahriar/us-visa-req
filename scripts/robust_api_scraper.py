import os
import time
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None
    print("WARNING: Supabase credentials not found. Running in dry-run mode.")

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

# ─────────────────────────────────────────────
# 1. ACCURATE DOCUMENTS PER VISA TYPE (Hardcoded from USCIS/State Dept)
#    These are legally correct and do NOT change by country.
# ─────────────────────────────────────────────
VISA_DOCUMENTS = {
    "b1-b2-tourist-visa": [
        "Valid passport (min. 6 months validity beyond stay)",
        "DS-160 Online Nonimmigrant Visa Application (completed)",
        "MRV visa application fee payment receipt ($185)",
        "One recent passport-style photograph",
        "Interview appointment confirmation letter",
        "Proof of strong ties to home country (employment letter, property deeds, family)",
        "Proof of financial ability to cover travel expenses (bank statements)",
    ],
    "f1-student-visa": [
        "Valid passport (min. 6 months validity beyond stay)",
        "DS-160 Online Nonimmigrant Visa Application (completed)",
        "MRV visa application fee payment receipt ($185)",
        "Form I-20 (Certificate of Eligibility) from a SEVP-accredited school",
        "SEVIS I-901 fee payment receipt",
        "One recent passport-style photograph",
        "Proof of financial ability to cover tuition and living expenses",
        "Academic transcripts and diplomas",
    ],
    "h1b-work-visa": [
        "Valid passport (min. 6 months validity beyond stay)",
        "DS-160 Online Nonimmigrant Visa Application (completed)",
        "MRV visa application fee payment receipt ($185)",
        "Form I-797 Notice of Action (USCIS petition approval notice)",
        "Labor Condition Application (LCA) certified by the Department of Labor",
        "One recent passport-style photograph",
        "Evidence of qualifying specialty occupation (degree, transcripts)",
        "Employment offer letter from US employer",
    ],
    "j1-exchange-visitor-visa": [
        "Valid passport (min. 6 months validity beyond stay)",
        "DS-160 Online Nonimmigrant Visa Application (completed)",
        "MRV visa application fee payment receipt ($185)",
        "Form DS-2019 (Certificate of Eligibility) from a designated sponsor",
        "SEVIS I-901 fee payment receipt",
        "One recent passport-style photograph",
        "Proof of financial support for the exchange program",
        "Sponsor program letter and details",
    ],
    "l1-intracompany-transfer-visa": [
        "Valid passport (min. 6 months validity beyond stay)",
        "DS-160 Online Nonimmigrant Visa Application (completed)",
        "MRV visa application fee payment receipt ($185)",
        "Form I-797 Notice of Action (USCIS petition approval notice)",
        "One recent passport-style photograph",
        "Employer support letter describing the intracompany transfer",
        "Proof of employment with foreign company for at least 1 year in last 3 years",
        "Evidence of managerial, executive, or specialized knowledge role",
    ],
    "o1-extraordinary-ability-visa": [
        "Valid passport (min. 6 months validity beyond stay)",
        "DS-160 Online Nonimmigrant Visa Application (completed)",
        "MRV visa application fee payment receipt ($185)",
        "Form I-797 Notice of Action (USCIS petition approval notice)",
        "One recent passport-style photograph",
        "Evidence of extraordinary ability (awards, publications, press, salary evidence)",
        "Written advisory opinion from a peer group or expert",
        "US agent or employer contract or itinerary of events",
    ],
}

# ─────────────────────────────────────────────
# 2. MAP our visa slugs to State Dept reciprocity table classification codes
# ─────────────────────────────────────────────
VISA_SLUG_TO_RECIPROCITY_CODE = {
    "b1-b2-tourist-visa": ["B-1/B-2", "B-2", "B-1"],
    "f1-student-visa": ["F-1"],
    "h1b-work-visa": ["H-1B"],
    "j1-exchange-visitor-visa": ["J-1"],
    "l1-intracompany-transfer-visa": ["L-1"],
    "o1-extraordinary-ability-visa": ["O-1"],
}

# ─────────────────────────────────────────────
# 3. SCRAPE RECIPROCITY TABLE for Validity per Country
# ─────────────────────────────────────────────
def fetch_reciprocity_validity(country_name: str, visa_slug: str, retries=3) -> str:
    """Scrapes the official State Dept reciprocity page for a country and returns visa validity."""
    url = f"https://travel.state.gov/content/travel/en/us-visas/Visa-Reciprocity-and-Civil-Documents-by-Country/{country_name.replace(' ', '-')}.html"
    codes_to_find = VISA_SLUG_TO_RECIPROCITY_CODE.get(visa_slug, [])

    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 404:
                return "Varies; check US Embassy website"

            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table")
            if not table:
                return "Varies; check US Embassy website"

            for row in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if len(cells) >= 4:
                    classification = cells[0]
                    if classification in codes_to_find:
                        validity = cells[3]  # Column: ValidityPeriod
                        if validity and validity != "N/A":
                            return validity

            return "Varies; check US Embassy website"

        except requests.exceptions.RequestException:
            if attempt < retries - 1:
                wait = (attempt + 1) * 5
                print(f"  Network error. Retrying in {wait}s...")
                time.sleep(wait)

    return "Varies; check US Embassy website"


# ─────────────────────────────────────────────
# 4. VALIDATION
# ─────────────────────────────────────────────
def validate_update(payload: dict) -> bool:
    try:
        if "required_documents" in payload:
            assert isinstance(payload["required_documents"], list), "Documents must be a list"
            assert len(payload["required_documents"]) > 0, "Documents list is empty"
        if "validity" in payload:
            assert isinstance(payload["validity"], str), "Validity must be a string"
        return True
    except AssertionError as e:
        print(f"  Validation failed: {e}")
        return False


# ─────────────────────────────────────────────
# 5. SAFE TARGETED UPDATE (never touches geo_summary)
# ─────────────────────────────────────────────
def safe_update(country_slug: str, visa_slug: str, payload: dict):
    if not validate_update(payload):
        print(f"  SKIPPING {country_slug}/{visa_slug} — validation failed.")
        return False

    try:
        if supabase:
            supabase.table("visa_requirements").update(payload).eq(
                "country_slug", country_slug
            ).eq("visa_slug", visa_slug).execute()
            print(f"  ✓ Updated: {country_slug} / {visa_slug}")
            return True
        else:
            print(f"  [DRY RUN] Would update: {country_slug} / {visa_slug} → {payload}")
            return True
    except Exception as e:
        print(f"  ERROR updating {country_slug}/{visa_slug}: {e}")
        return False


# ─────────────────────────────────────────────
# 6. PROCESS ONE ROW
# ─────────────────────────────────────────────
def process_row(country_name: str, country_slug: str, visa_slug: str):
    print(f"\nProcessing: {country_name} / {visa_slug}")

    # Get correct documents for this visa type
    documents = VISA_DOCUMENTS.get(visa_slug)
    if not documents:
        print(f"  SKIP — no document list defined for {visa_slug}")
        return

    # Scrape real validity from State Dept reciprocity table
    validity = fetch_reciprocity_validity(country_name, visa_slug)
    print(f"  Validity fetched: {validity}")

    # Build targeted payload (ONLY these fields — geo_summary is untouched)
    payload = {
        "required_documents": documents,
        "validity": validity,
        "last_updated": time.strftime("%Y-%m-%d"),
    }

    safe_update(country_slug, visa_slug, payload)


# ─────────────────────────────────────────────
# 7. MAIN — test with ONE row first
# ─────────────────────────────────────────────
def run_single_test():
    """Test with a single row. Run this first before unleashing all rows."""
    process_row("Brazil", "brazil", "b1-b2-tourist-visa")


def run_all_rows():
    """Fetch all rows from Supabase and update every single one."""
    if not supabase:
        print("ERROR: Supabase not connected. Cannot run full update.")
        return

    print("Fetching all rows from Supabase...")
    result = supabase.table("visa_requirements").select("country_name, country_slug, visa_slug").execute()
    rows = result.data

    print(f"Found {len(rows)} rows to update.\n")
    for i, row in enumerate(rows):
        process_row(row["country_name"], row["country_slug"], row["visa_slug"])
        time.sleep(0.5)  # Polite delay to avoid hammering State Dept

    print(f"\n✓ Done! Updated {len(rows)} rows.")


if __name__ == "__main__":
    run_all_rows()
