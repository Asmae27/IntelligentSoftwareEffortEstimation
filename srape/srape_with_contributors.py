import requests
import csv
import time
import os
from urllib.parse import urlparse

# ==========================
# CONFIG
# ==========================
TOKEN = os.getenv("GITHUB_TOKEN")

INPUT_CSV = "dataset/github_graphql_balanced_dataset.csv"
OUTPUT_CSV = "dataset/github_graphql_with_contributors.csv"

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json"
}

SLEEP_TIME = 0.5  # to avoid rate limits

# ==========================
# Extract owner/repo from URL
# ==========================
def extract_repo_info(repo_url):
    parts = urlparse(repo_url).path.strip("/").split("/")
    return parts[0], parts[1]

# ==========================
# Get contributors count
# ==========================
def get_contributors_count(repo_url):
    try:
        owner, repo = extract_repo_info(repo_url)

        url = f"https://api.github.com/repos/{owner}/{repo}/contributors"
        params = {"per_page": 1, "anon": "true"}

        response = requests.get(url, headers=HEADERS, params=params)

        if response.status_code != 200:
            print(f" Error {response.status_code} for {repo_url}")
            return 0

        if "Link" in response.headers:
            links = response.headers["Link"]
            for link in links.split(","):
                if 'rel="last"' in link:
                    last_url = link.split(";")[0].strip("<> ")
                    last_page = int(last_url.split("page=")[-1])
                    return last_page

        return len(response.json())

    except Exception as e:
        print(f" Failed for {repo_url}: {e}")
        return 0

# ==========================
# Load already processed URLs
# ==========================
def load_processed_urls():
    processed = set()

    if os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                processed.add(row["url"])

    return processed

# ==========================
# Main Processing
# ==========================
def main():
    print(" Reading dataset...")

    with open(INPUT_CSV, "r", newline="", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames + ["contributors"]
        rows = list(reader)

    processed_urls = load_processed_urls()
    print(f" Already processed: {len(processed_urls)} repos")

    # Check if file exists → decide write or append
    file_exists = os.path.exists(OUTPUT_CSV)

    mode = "a" if file_exists else "w"

    with open(OUTPUT_CSV, mode, newline="", encoding="utf-8") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)

        # Write header only if file is new
        if not file_exists:
            writer.writeheader()

        total = len(rows)
        count = 0

        for i, row in enumerate(rows):
            repo_url = row["url"]

            # Skip already processed
            if repo_url in processed_urls:
                continue

            count += 1
            print(f"[{count}] Fetching: {repo_url}")

            contributors = get_contributors_count(repo_url)
            row["contributors"] = contributors

            writer.writerow(row)

            time.sleep(SLEEP_TIME)

    print(f"\n Done! Data saved in: {OUTPUT_CSV}")

# ==========================
# RUN
# ==========================
if __name__ == "__main__":
    main()