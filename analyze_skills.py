"""
Count how often in-demand skills appear in the job postings saved by fetch_jobs.py.

Phase 1 of the AWS Job Market Tracker. Reads every file in data/raw/,
removes duplicate postings, and reports the share of postings that mention
each skill, broken down by job title. Results are also written to
data/processed/ (later this becomes the "processed" zone in S3).

Usage:
    python analyze_skills.py
"""

import csv
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
TOP_N = 15

# Skill name -> phrases that count as a mention (matched case-insensitively,
# as whole words, so "Java" won't match "JavaScript").
SKILLS = {
    # Cloud
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"],
    "GCP": ["gcp", "google cloud"],
    # Languages
    "Python": ["python"],
    "SQL": ["sql"],
    "Java": ["java"],
    "JavaScript": ["javascript", "node.js", "nodejs"],
    "TypeScript": ["typescript"],
    "Go": ["golang"],
    "C++": ["c++"],
    "C#": ["c#"],
    "Scala": ["scala"],
    "Rust": ["rust"],
    # Infrastructure / DevOps
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Terraform": ["terraform"],
    "CI/CD": ["ci/cd", "cicd", "continuous integration"],
    "Linux": ["linux"],
    "Git": ["git", "github", "gitlab"],
    # Data
    "Spark": ["spark", "pyspark"],
    "Kafka": ["kafka"],
    "Airflow": ["airflow"],
    "Snowflake": ["snowflake"],
    "Databricks": ["databricks"],
    "dbt": ["dbt"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MongoDB": ["mongodb"],
    # AI / ML
    "Machine Learning": ["machine learning"],
    "AI / LLMs": ["llm", "llms", "generative ai", "genai"],
}


def build_patterns():
    """Compile one regex per skill. Custom boundaries handle names like C++ and CI/CD."""
    patterns = {}
    for skill, phrases in SKILLS.items():
        alternatives = "|".join(re.escape(p) for p in phrases)
        patterns[skill] = re.compile(
            rf"(?<![a-z0-9])(?:{alternatives})(?![a-z0-9])", re.IGNORECASE
        )
    return patterns


def load_postings():
    """Read every raw file and return {search_term: {posting_id: posting}}, deduplicated."""
    postings = defaultdict(dict)
    files = sorted(RAW_DIR.glob("*/*.json"))
    if not files:
        raise SystemExit("No data found. Run fetch_jobs.py first.")

    for path in files:
        payload = json.loads(path.read_text())
        term = payload["search_term"]
        for job in payload["results"]:
            postings[term].setdefault(job["id"], job)  # same id seen twice = one posting
    return postings, len(files)


def count_skills(jobs, patterns):
    """Return {skill: number of postings mentioning it}."""
    counts = defaultdict(int)
    for job in jobs:
        text = f"{job.get('title', '')} {job.get('description', '')}"
        for skill, pattern in patterns.items():
            if pattern.search(text):
                counts[skill] += 1
    return counts


def salary_summary(jobs):
    """Median salary midpoint, using only salaries the employer actually stated."""
    midpoints = []
    for job in jobs:
        if str(job.get("salary_is_predicted")) == "1":
            continue  # Adzuna estimated this one; skip it
        low, high = job.get("salary_min"), job.get("salary_max")
        if low and high:
            midpoints.append((low + high) / 2)
    if not midpoints:
        return None, 0
    return statistics.median(midpoints), len(midpoints)


def print_report(term, total, counts, median_salary, salary_n):
    print(f"\n=== {term.title()} ({total} postings) ===")
    if median_salary:
        print(f"Median stated salary: ${median_salary:,.0f} (from {salary_n} postings)")
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N]
    for skill, count in ranked:
        pct = 100 * count / total
        bar = "#" * round(pct / 2)
        print(f"  {skill:<17} {pct:5.1f}%  {bar}")


def save_results(rows):
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / "skills_summary.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["search_term", "skill", "postings_mentioning", "total_postings", "percent"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def main():
    patterns = build_patterns()
    postings, file_count = load_postings()
    print(f"Loaded {file_count} files.")
    print("Note: Adzuna descriptions are truncated, so these percentages undercount real demand.")

    rows = []
    for term, jobs_by_id in sorted(postings.items()):
        jobs = list(jobs_by_id.values())
        total = len(jobs)
        counts = count_skills(jobs, patterns)
        median_salary, salary_n = salary_summary(jobs)
        print_report(term, total, counts, median_salary, salary_n)

        for skill in SKILLS:
            rows.append({
                "search_term": term,
                "skill": skill,
                "postings_mentioning": counts.get(skill, 0),
                "total_postings": total,
                "percent": round(100 * counts.get(skill, 0) / total, 1),
            })

    path = save_results(rows)
    print(f"\nSaved full results -> {path}")


if __name__ == "__main__":
    main()
