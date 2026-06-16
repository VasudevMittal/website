import os
import json
import time
import requests

# =========================
# CONFIG
# =========================

ADS_TOKEN = os.environ["ADS_TOKEN"]
ORCID_ID = "0000-0002-1708-6088"
MY_NAME = "Vasudev Mittal"  # change this to your name as it appears in ADS (e.g. "V. Mittal", "Mittal, V.", etc.)

ADS_URL = "https://api.adsabs.harvard.edu/v1/search/query"
ORCID_URL = f"https://pub.orcid.org/v3.0/{ORCID_ID}/works"

ads_headers = {
    "Authorization": f"Bearer {ADS_TOKEN}"
}

orcid_headers = {
    "Accept": "application/json"
}

# =========================
# UTILITIES
# =========================

def normalize_doi(doi):
    if not doi:
        return None
    return doi.lower().replace("https://doi.org/", "").strip()


def is_alphabetical(authors):
    if not authors:
        return False
    last_names = [a.split(",")[0].strip().lower() for a in authors]
    return last_names == sorted(last_names)

def classify_authorship(authors, my_name):
    if not authors:
        return "collaboration", None

    # normalize better
    authors_norm = [a.lower().replace(".", "") for a in authors]
    my_norm = my_name.lower().replace(".", "")

    # stronger matching: last-name match
    my_last = my_norm.split()[-1]

    match_index = None
    for i, a in enumerate(authors_norm):
        if my_last in a:
            match_index = i
            break

    if match_index is None:
        return "collaboration", None

    if match_index == 0:
        return "first_author", 1
    elif match_index == 1:
        return "second_author", 2
    else:
        return "collaboration", match_index + 1


# =========================
# ORCID FETCH
# =========================

def fetch_orcid_works(orcid_id):
    r = requests.get(ORCID_URL, headers=orcid_headers)
    r.raise_for_status()
    data = r.json()

    works = []

    for group in data.get("group", []):
        summary = group.get("work-summary", [{}])[0]

        title = summary.get("title", {}).get("title", {}).get("value", "")

        ext_ids = summary.get("external-ids", {}).get("external-id", [])

        doi = None
        for eid in ext_ids:
            if eid.get("external-id-type", "").lower() == "doi":
                doi = eid.get("external-id-value")

        works.append({
            "title": title,
            "doi": normalize_doi(doi)
        })

    return works


# =========================
# ADS FETCH (BY DOI)
# =========================

def fetch_ads_by_doi(doi):
    if not doi:
        return None

    params = {
        "q": f"doi:{doi}",
        "fl": "title,author,pub,citation_count,doi,year,bibyear",
        "rows": 1
    }

    r = requests.get(ADS_URL, headers=ads_headers, params=params)
    r.raise_for_status()

    docs = r.json().get("response", {}).get("docs", [])
    return docs[0] if docs else None

def extract_year(ads_doc):
    if not ads_doc:
        return None
    return ads_doc.get("year") or ads_doc.get("bibyear")

# =========================
# MERGE FUNCTION
# =========================

def merge_record(orcid_work, ads_doc):
    if ads_doc:
        return {
            "title": (ads_doc.get("title") or [orcid_work["title"]])[0],
            "authors": ads_doc.get("author", []),
            "journal": ads_doc.get("pub", ""),
            "doi": normalize_doi(orcid_work.get("doi")),
            "citations": ads_doc.get("citation_count", 0),
            "year": extract_year(ads_doc)
        }

    # fallback if ADS missing
    return {
        "title": orcid_work["title"],
        "authors": [],
        "journal": "",
        "doi": normalize_doi(orcid_work.get("doi")),
        "citations": 0,
        "year": extract_year(ads_doc)
    }


# =========================
# MAIN PIPELINE
# =========================

def main():

    print("Fetching ORCID works...")
    orcid_works = fetch_orcid_works(ORCID_ID)

    output = {
        "first_author": [],
        "second_author": [],
        "collaboration": []
    }

    print(f"Found {len(orcid_works)} ORCID works")

    for i, work in enumerate(orcid_works):

        doi = work.get("doi")
        ads_doc = fetch_ads_by_doi(doi) if doi else None

        merged = merge_record(work, ads_doc)

        authors = merged.get("authors", [])
        category, position = classify_authorship(authors, MY_NAME)

        entry = {
            "title": merged["title"],
            "authors": authors,
            "journal": merged["journal"],
            "doi": merged["doi"],
            "citations": merged["citations"],
            "position": position,
            "total_authors": len(authors),
            "alphabetical": is_alphabetical(authors),
            "year": merged["year"]
        }

        output[category].append(entry)

        # avoid ADS rate limits
        time.sleep(0.2)

    # =========================
    # SORTING RULES
    # =========================

    output["first_author"].sort(key=lambda x: x["citations"], reverse=True)
    output["second_author"].sort(key=lambda x: x["citations"], reverse=True)
    output["collaboration"].sort(key=lambda x: x["citations"], reverse=True)

    # =========================
    # SAVE FOR HUGO
    # =========================

    os.makedirs("data", exist_ok=True)

    with open("data/publications.json", "w") as f:
        json.dump(output, f, indent=2)

    print("Done → data/publications.json")


if __name__ == "__main__":
    main()