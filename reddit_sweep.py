import os, csv
from datetime import datetime
import praw


SUBREDDITS = [
    "UFOs",
    "HighStrangeness",
    "aliens",
    "UFOsOpenMinds",
    "PuertoRico",
    "Caribbean"
]

KEYWORDS = [
    "UFO Puerto Rico",
    "OVNI Puerto Rico",
    "UAP Puerto Rico",
    "USO Puerto Rico",
    "strange lights Puerto Rico",
    "anomalous lights Puerto Rico",
    "luces extrañas Puerto Rico"
]

LIMIT = 500  # results per keyword per subreddit


def sweep(start, end, outfile):
    """Perform a timeline-bounded Reddit sweep."""
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")

    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent="pruap-cloud/1.0"
    )

    rows = []

    for sub in SUBREDDITS:
        subreddit = reddit.subreddit(sub)
        for kw in KEYWORDS:
            print(f"Searching r/{sub} for '{kw}'...")

            try:
                for post in subreddit.search(kw, sort="new", limit=LIMIT):
                    created = datetime.utcfromtimestamp(post.created_utc)

                    if created < start_dt or created > end_dt:
                        continue

                    rows.append({
                        "id": post.id,
                        "created": created.isoformat(),
                        "subreddit": sub,
                        "keyword": kw,
                        "title": post.title,
                        "text": post.selftext or "",
                        "url": f"https://www.reddit.com{post.permalink}",
                        "comments": post.num_comments,
                        "score": post.score
                    })

            except Exception as e:
                print(f"Error scraping r/{sub}: {e}")

    if not rows:
        print("\nNo results found for this window.")
        return

    with open(outfile, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    print(f"\nSaved {len(rows)} rows to {outfile}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()

    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--out", default="output.csv")

    args = p.parse_args()
    sweep(args.start, args.end, args.out)
