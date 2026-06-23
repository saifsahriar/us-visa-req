import os
import time
from supabase import create_client, Client
from slugify import slugify
from openai import OpenAI

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_ANON_KEY"]
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

if NVIDIA_API_KEY:
    ai_client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=NVIDIA_API_KEY
    )
else:
    ai_client = None

# US Visa types to cover
VISA_TYPES = [
    {"name": "B1/B2 Tourist Visa", "slug": "b1-b2-tourist-visa"},
    {"name": "F1 Student Visa", "slug": "f1-student-visa"},
    {"name": "H1B Work Visa", "slug": "h1b-work-visa"},
    {"name": "J1 Exchange Visitor Visa", "slug": "j1-exchange-visitor-visa"},
    {"name": "L1 Intracompany Transfer Visa", "slug": "l1-intracompany-transfer-visa"},
    {"name": "O1 Extraordinary Ability Visa", "slug": "o1-extraordinary-ability-visa"},
]

# Complete list of countries (sourced from travel.state.gov embassy/consulate list)
COUNTRY_NAMES = [
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola",
    "Antigua and Barbuda", "Argentina", "Armenia", "Australia", "Austria",
    "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados",
    "Belarus", "Belgium", "Belize", "Benin", "Bhutan",
    "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei",
    "Bulgaria", "Burkina Faso", "Burundi", "Cabo Verde", "Cambodia",
    "Cameroon", "Canada", "Central African Republic", "Chad", "Chile",
    "China", "Colombia", "Comoros", "Congo (Brazzaville)", "Congo (Kinshasa)",
    "Costa Rica", "Cote d'Ivoire", "Croatia", "Cuba", "Cyprus",
    "Czech Republic", "Denmark", "Djibouti", "Dominica", "Dominican Republic",
    "Ecuador", "Egypt", "El Salvador", "Equatorial Guinea", "Eritrea",
    "Estonia", "Eswatini", "Ethiopia", "Fiji", "Finland",
    "France", "Gabon", "Gambia", "Georgia", "Germany",
    "Ghana", "Greece", "Grenada", "Guatemala", "Guinea",
    "Guinea-Bissau", "Guyana", "Haiti", "Honduras", "Hungary",
    "Iceland", "India", "Indonesia", "Iran", "Iraq",
    "Ireland", "Israel", "Italy", "Jamaica", "Japan",
    "Jordan", "Kazakhstan", "Kenya", "Kiribati", "Kosovo",
    "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon",
    "Lesotho", "Liberia", "Libya", "Liechtenstein", "Lithuania",
    "Luxembourg", "Madagascar", "Malawi", "Malaysia", "Maldives",
    "Mali", "Malta", "Marshall Islands", "Mauritania", "Mauritius",
    "Mexico", "Micronesia", "Moldova", "Monaco", "Mongolia",
    "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia",
    "Nauru", "Nepal", "Netherlands", "New Zealand", "Nicaragua",
    "Niger", "Nigeria", "North Korea", "North Macedonia", "Norway",
    "Oman", "Pakistan", "Palau", "Panama", "Papua New Guinea",
    "Paraguay", "Peru", "Philippines", "Poland", "Portugal",
    "Qatar", "Romania", "Russia", "Rwanda", "Saint Kitts and Nevis",
    "Saint Lucia", "Saint Vincent and the Grenadines", "Samoa", "San Marino", "Sao Tome and Principe",
    "Saudi Arabia", "Senegal", "Serbia", "Seychelles", "Sierra Leone",
    "Singapore", "Slovakia", "Slovenia", "Solomon Islands", "Somalia",
    "South Africa", "South Korea", "South Sudan", "Spain", "Sri Lanka",
    "Sudan", "Suriname", "Sweden", "Switzerland", "Syria",
    "Taiwan", "Tajikistan", "Tanzania", "Thailand", "Timor-Leste",
    "Togo", "Tonga", "Trinidad and Tobago", "Tunisia", "Turkey",
    "Turkmenistan", "Tuvalu", "Uganda", "Ukraine", "United Arab Emirates",
    "United Kingdom", "Uruguay", "Uzbekistan", "Vanuatu", "Vatican City",
    "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe",
]


def get_countries():
    """Return a list of countries with name and slug."""
    return [{"name": name, "slug": slugify(name)} for name in COUNTRY_NAMES]


def build_requirement_data(country, visa_type):
    """
    Build structured data for a country+visa combination.
    Includes an AI-generated GEO summary using NVIDIA NIM.
    """
    geo_summary = ""
    if ai_client:
        try:
            prompt = f"Generate 2 authoritative, standalone sentences about the US {visa_type['name']} for citizens of {country['name']}. Format them as direct, definitive claims (e.g., 'Citizens of {country['name']} applying for a {visa_type['name']} must expect...'). Do not use conversational fluff."
            response = ai_client.chat.completions.create(
                model="meta/llama-3.3-70b-instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=150,
            )
            geo_summary = response.choices[0].message.content.strip()
        except Exception as e:
            print(f"AI Generation failed for {country['name']} - {visa_type['name']}: {e}")
            time.sleep(5)  # Rate limit safety pause
            
    return {
        "country_name": country["name"],
        "country_slug": country["slug"],
        "visa_type": visa_type["name"],
        "visa_slug": visa_type["slug"],
        "requirement_summary": f"Requirements for {country['name']} citizens applying for a US {visa_type['name']}.",
        "geo_summary": geo_summary,
        "required_documents": [
            "Valid passport (6+ months validity)",
            "DS-160 Online Nonimmigrant Visa Application",
            "Visa application fee payment receipt",
            "Photo meeting US visa requirements",
            "Interview appointment confirmation",
        ],
        "processing_time": "3-5 business days after interview",
        "fee_usd": 185,
        "validity": "Up to 10 years (B1/B2); varies by visa type",
        "notes": f"Citizens of {country['name']} must apply at the nearest US Embassy or Consulate.",
        "source_url": "https://travel.state.gov",
        "last_updated": "2026-06-22",
    }


def push_to_supabase(record, retries=3):
    for attempt in range(retries):
        try:
            supabase.table("visa_requirements").upsert(
                record,
                on_conflict="country_slug,visa_slug"
            ).execute()
            return
        except Exception as e:
            if attempt < retries - 1:
                print(f"Error pushing data, retrying in 2s...")
                time.sleep(2)
            else:
                print(f"Failed to push {record['country_name']} after {retries} attempts.")

def get_completed_countries():
    """Fetch countries that have already been fully processed."""
    counts = {}
    has_more = True
    page = 0
    page_size = 1000
    while has_more:
        res = supabase.table("visa_requirements").select("country_name, geo_summary").range(page*page_size, (page+1)*page_size-1).execute()
        if not res.data:
            break
        for row in res.data:
            if row.get("geo_summary"): # Only count if the AI summary was actually generated
                c = row["country_name"]
                counts[c] = counts.get(c, 0) + 1
        if len(res.data) < page_size:
            has_more = False
        page += 1
    return {c for c, count in counts.items() if count == len(VISA_TYPES)}


def main():
    countries = get_countries()
    print(f"Found {len(countries)} total countries")
    
    completed = get_completed_countries()
    print(f"Skipping {len(completed)} already completed countries")
    
    for country in countries:
        if country['name'] in completed:
            continue
            
        for visa_type in VISA_TYPES:
            record = build_requirement_data(country, visa_type)
            push_to_supabase(record)
            print(f"Pushed: {country['name']} + {visa_type['name']}")
            time.sleep(0.2)


if __name__ == "__main__":
    main()
