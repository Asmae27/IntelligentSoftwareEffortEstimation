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
OUTPUT_CSV = "dataset/github_graphql_python.csv"

LANGUAGES = ["Python"]
YEARS = list(range(2019, 2024))

STAR_RANGES = [
    (0, 50),
    (50, 500),
    (500, 1000000)
]

MAX_PAGES = 50
REPOS_PER_PAGE = 50
MIN_LOC = 1000
MIN_DISK_USAGE_KB = MIN_LOC // 12

# ✅ FIX 1: Added contributors to FIELDNAMES
FIELDNAMES = [
    "name", "url", "stars", "forks", "size_kb", "language",
    "created_at", "updated_at", "issues", "pull_requests", "commits",
    "estimated_loc", "commit_frequency", "activity_level",
    "project_maturity", "contributors"
]

# ==========================
# GraphQL Query
# ✅ FIX 2: Added contributors (mentionableUsers) to the query
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
        issues(states: OPEN) { totalCount }
        pullRequests(states: OPEN) { totalCount }
        mentionableUsers { totalCount }
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 1) { totalCount }
            }
          }
        }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
""" % REPOS_PER_PAGE


# ==========================
# Feature computation
# ✅ FIX 3: activity_level based on commit_frequency, not raw commits
# ✅ FIX 4: project_maturity uses broader age ranges
# ==========================
def compute_features(repo):
    created = datetime.strptime(repo["created_at"], "%Y-%m-%dT%H:%M:%SZ")
    months = max((datetime.now() - created).days / 30, 1)
    commits = repo["commits"]
    freq = commits / months  # commits per month

    repo["estimated_loc"]    = repo["size_kb"] * 12
    repo["commit_frequency"] = round(freq, 6)

    # ✅ Based on frequency, not raw count
    repo["activity_level"] = (
        "low"    if freq < 1  else
        "medium" if freq < 10 else
        "high"
    )

    # ✅ Broader ranges so not everything is "mature"
    repo["project_maturity"] = (
        "new"     if months < 12 else
        "growing" if months < 48 else
        "mature"
    )
    return repo


# ==========================
# GitHub GraphQL Request
# ✅ FIX 5: Added retry logic on connection drop — no silent zeros
# ==========================
def run_query(query, variables, retries=3, wait=5):
    for attempt in range(retries):
        try:
            response = requests.post(
                URL, headers=HEADERS,
                json={"query": query, "variables": variables},
                timeout=30
            )
            data = response.json()
            if "errors" in data:
                raise Exception(data["errors"])
            return data
        except Exception as e:
            print(f"  ⚠️  Attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(wait)
            else:
                print("  ❌ All retries failed — skipping this page")
                return None


# ==========================
# Main Pipeline
# ==========================
def main():
    # Write header once
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

    for lang in LANGUAGES:
        for year in YEARS:
            for star_min, star_max in STAR_RANGES:
                search_query = (
                    f"language:{lang} created:{year}-01-01..{year}-12-31 "
                    f"stars:{star_min}..{star_max} size:>{MIN_DISK_USAGE_KB}"
                )
                print(f"\n🔍 {lang} | {year} | stars {star_min}–{star_max}")

                cursor = None
                page = 1

                while page <= MAX_PAGES:
                    print(f"   📄 Page {page}...")
                    variables = {"query": search_query, "after": cursor}

                    # ✅ FIX 5: run_query returns None on failure instead of crashing
                    data = run_query(QUERY, variables)
                    if data is None:
                        break

                    rate = data.get("data", {}).get("rateLimit", {})
                    print(f"   ⚡ API cost={rate.get('cost')} | remaining={rate.get('remaining')}")

                    repos = data["data"]["search"]["nodes"]

                    for r in repos:
                        try:
                            if not r or r.get("diskUsage", 0) < MIN_DISK_USAGE_KB:
                                continue

                            # ✅ FIX 6: contributors — skip row if missing, never write 0
                            contributors = r.get("mentionableUsers", {}).get("totalCount")
                            if contributors is None:
                                print(f"   ⚠️  Skipping {r.get('name')} — contributors unavailable")
                                continue

                            repo_data = {
                                "name":          r["name"],
                                "url":           r["url"],
                                "stars":         r["stargazerCount"],
                                "forks":         r["forkCount"],
                                "size_kb":       r["diskUsage"],
                                "language":      r["primaryLanguage"]["name"] if r["primaryLanguage"] else None,
                                "created_at":    r["createdAt"],
                                "updated_at":    r["updatedAt"],
                                "issues":        r["issues"]["totalCount"],
                                "pull_requests": r["pullRequests"]["totalCount"],
                                "commits":       (
                                    r["defaultBranchRef"]["target"]["history"]["totalCount"]
                                    if r["defaultBranchRef"] else None  # ✅ None not 0
                                ),
                                "contributors":  contributors,
                            }

                            # ✅ FIX 7: Skip rows where commits is None
                            if repo_data["commits"] is None:
                                print(f"   ⚠️  Skipping {r['name']} — commits unavailable")
                                continue

                            repo_data = compute_features(repo_data)

                            with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
                                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                                writer.writerow(repo_data)

                        except Exception as e:
                            print(f"   ❌ Skipped repo: {e}")
                            continue

                    page_info = data["data"]["search"]["pageInfo"]
                    if not page_info["hasNextPage"]:
                        break

                    cursor = page_info["endCursor"]
                    page += 1
                    time.sleep(1)

    print(f"\n✅ Done. Saved to: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()