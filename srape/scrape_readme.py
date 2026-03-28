import pandas as pd
import requests
import base64
from urllib.parse import urlparse
import time
import os

# ==========================
# CONFIG
# ==========================
INPUT_FILE = "dataset/github_graphql_with_contributors.csv"
OUTPUT_FILE = "dataset/dataset_with_readme.csv"
CHECKPOINT_FILE = "dataset/checkpoint.csv"
 
TOKEN = os.getenv("GITHUB_TOKEN")
SAVE_EVERY = 50                  # Save progress every N repos
MAX_README_LENGTH = 5000         # Limit size for performance

# ==========================
# Extract owner/repo
# ==========================
def extract_repo_info(repo_url):
    parts = urlparse(repo_url).path.strip("/").split("/")
    return parts[0], parts[1]

# ==========================
# Clean README (basic)
# ==========================
def clean_readme(text):
    if not isinstance(text, str):
        return ""

    # Remove markdown symbols (basic cleaning)
    text = text.replace("#", "")
    text = text.replace("```", "")
    text = text.replace("*", "")
    text = text.replace("-", " ")

    return text.strip()

# ==========================
# Get README from GitHub API
# ==========================
def get_readme(owner, repo, token=None):
    url = f"https://api.github.com/repos/{owner}/{repo}/readme"

    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            content = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")

            #  Limit size (Performance Tip)
            content = content[:MAX_README_LENGTH]

            #  Clean text
            content = clean_readme(content)

            return content

        elif response.status_code == 404:
            return "No README"

        else:
            return f"Error {response.status_code}"

    except Exception as e:
        return "Error"

# ==========================
# Load dataset (with checkpoint support)
# ==========================
if os.path.exists(CHECKPOINT_FILE):
    print(" Resuming from checkpoint...")
    df = pd.read_csv(CHECKPOINT_FILE)
else:
    df = pd.read_csv(INPUT_FILE)
    df["readme"] = None

# ==========================
# MAIN LOOP
# ==========================
for i in range(len(df)):
    if pd.notna(df.loc[i, "readme"]):
        continue  # Skip already processed rows

    repo_url = df.loc[i, "url"]

    try:
        owner, repo = extract_repo_info(repo_url)
        readme = get_readme(owner, repo, TOKEN)
    except:
        readme = "Error"

    df.loc[i, "readme"] = readme

    print(f"{i+1}/{len(df)} processed")

    # ==========================
    #  Save checkpoint regularly
    # ==========================
    if (i + 1) % SAVE_EVERY == 0:
        df.to_csv(CHECKPOINT_FILE, index=False)
        print(" Checkpoint saved")

    # ==========================
    #  Rate limit protection
    # ==========================
    time.sleep(0.2)

# ==========================
# Final save
# ==========================
df.to_csv(OUTPUT_FILE, index=False)

# Remove checkpoint if done
if os.path.exists(CHECKPOINT_FILE):
    os.remove(CHECKPOINT_FILE)

print(" Done! Dataset ready.")