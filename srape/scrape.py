import requests
import csv
from datetime import datetime
import time
import os
# ==========================
# CONFIG
# ==========================

TOKEN = os.getenv("GITHUB_TOKEN")

URL = "https://api.github.com/graphql"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

OUTPUT_CSV = "dataset\github_graphql_balanced_dataset.csv"

LANGUAGES = ["Python", "Java", "JavaScript"]
YEARS = list(range(2019, 2024))  # 2010-2023 inclusive

# Split by stars ranges
STAR_RANGES = [
    (0, 50),       # small/popular repos
    (50, 500),     # medium popularity
    (500, 1000000) # very popular
]

MAX_PAGES = 50       # per language/year/star_range
REPOS_PER_PAGE = 50   # max 100
MIN_LOC = 1000
MIN_DISK_USAGE_KB = MIN_LOC // 12  # approximate LOC

FIELDNAMES = [
    "name", "url", "stars", "forks", "size_kb", "language",
    "created_at", "updated_at", "issues", "pull_requests", "commits",
    "estimated_loc", "commit_frequency", "activity_level", "project_maturity"
]

# ==========================
# GraphQL Query
# ==========================
QUERY = """
query($query: String!, $after: String) {
  search(query: $query, type: REPOSITORY, first: %d, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on Repository {
        name
        url
        createdAt
        updatedAt
        stargazerCount
        forkCount
        diskUsage
        primaryLanguage { name }
        issues { totalCount }
        pullRequests { totalCount }
        defaultBranchRef { target { ... on Commit { history(first: 1) { totalCount } } } }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
""" % REPOS_PER_PAGE

# ==========================
# Feature computation
# ==========================
def compute_features(repo):
    created = datetime.strptime(repo["created_at"], "%Y-%m-%dT%H:%M:%SZ")
    months = max((datetime.now() - created).days / 30, 1)
    commits = repo["commits"]

    repo["estimated_loc"] = repo["size_kb"] * 12
    repo["commit_frequency"] = commits / months
    repo["activity_level"] = (
        "low" if commits < 50 else "medium" if commits < 200 else "high"
    )
    repo["project_maturity"] = (
        "new" if months < 6 else "growing" if months < 24 else "mature"
    )
    return repo

# ==========================
# GitHub GraphQL Request
# ==========================
def run_query(query, variables):
    response = requests.post(URL, headers=HEADERS, json={"query": query, "variables": variables})
    data = response.json()
    if "errors" in data:
        raise Exception(data["errors"])
    return data

# ==========================
# Initialize CSV
# ==========================
with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()

# ==========================
# Main Pipeline
# ==========================
def main():
    for lang in LANGUAGES:
        for year in YEARS:
            for star_min, star_max in STAR_RANGES:
                # GitHub search: language, year, stars
                search_query = f"language:{lang} created:{year}-01-01..{year}-12-31 stars:{star_min}..{star_max} size:>100"
                print(f"\n Searching {lang} for year {year} with stars {star_min}-{star_max}")

                cursor = None
                page = 1

                while page <= MAX_PAGES:
                    print(f" Fetching page {page}...")
                    variables = {"query": search_query, "after": cursor}

                    try:
                        data = run_query(QUERY, variables)
                    except Exception as e:
                        print("GraphQL query failed:", e)
                        break

                    rate_limit = data.get("data", {}).get("rateLimit", {})
                    print(f"API cost: {rate_limit.get('cost')}, remaining: {rate_limit.get('remaining')}")

                    repos = data["data"]["search"]["nodes"]

                    for r in repos:
                        try:
                            if r["diskUsage"] < MIN_DISK_USAGE_KB:
                                continue

                            repo_data = {
                                "name": r["name"],
                                "url": r["url"],
                                "stars": r["stargazerCount"],
                                "forks": r["forkCount"],
                                "size_kb": r["diskUsage"],
                                "language": r["primaryLanguage"]["name"] if r["primaryLanguage"] else None,
                                "created_at": r["createdAt"],
                                "updated_at": r["updatedAt"],
                                "issues": r["issues"]["totalCount"],
                                "pull_requests": r["pullRequests"]["totalCount"],
                                "commits": r["defaultBranchRef"]["target"]["history"]["totalCount"]
                                           if r["defaultBranchRef"] else 0
                            }

                            repo_data = compute_features(repo_data)

                            with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
                                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                                writer.writerow(repo_data)

                        except Exception as e:
                            print("Skipped repo due to error:", e)
                            continue

                    # Pagination
                    page_info = data["data"]["search"]["pageInfo"]
                    if not page_info["hasNextPage"]:
                        break

                    cursor = page_info["endCursor"]
                    page += 1
                    time.sleep(1)

    print(f"\n Data collection finished. CSV saved: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()