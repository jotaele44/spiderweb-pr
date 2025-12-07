import csv, glob

files = glob.glob("sweep_*.csv")
rows = []

print(f"Merging {len(files)} sweep files...")

for f in files:
    with open(f, encoding="utf-8") as infile:
        rows.extend(list(csv.DictReader(infile)))

if not rows:
    print("No sweep files found.")
    exit()

with open("PRUAP_MASTER_SOCIAL.csv", "w", newline="", encoding="utf-8") as out:
    w = csv.DictWriter(out, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)

print("Merged into PRUAP_MASTER_SOCIAL.csv")
