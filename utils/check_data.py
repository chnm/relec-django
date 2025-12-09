import csv

with open("static-data/schedules_with_datascribe.csv", "r") as f:
    reader = csv.DictReader(f)

    total = 0
    has_location = 0
    null_location = 0
    missing_location = 0
    illegible_location = 0
    empty_location = 0

    for row in reader:
        total += 1
        location_val = row.get("(d, e, f) Location", "")

        if location_val == "NULL":
            null_location += 1
        elif location_val == "MISSING":
            missing_location += 1
        elif location_val == "ILLEGIBLE":
            illegible_location += 1
        elif location_val == "" or location_val is None:
            empty_location += 1
        else:
            has_location += 1

    print(f"Total rows in CSV: {total:,}")
    print("\nLocation column breakdown:")
    print(f"  Has place_id: {has_location:,} ({has_location / total * 100:.1f}%)")
    print(f"  NULL: {null_location:,} ({null_location / total * 100:.1f}%)")
    print(f"  MISSING: {missing_location:,} ({missing_location / total * 100:.1f}%)")
    print(
        f"  ILLEGIBLE: {illegible_location:,} ({illegible_location / total * 100:.1f}%)"
    )
    print(f"  Empty: {empty_location:,} ({empty_location / total * 100:.1f}%)")
    print(
        f"\nWithout valid place_id: {
            null_location + missing_location + illegible_location + empty_location:,
        } ({
            (null_location + missing_location + illegible_location + empty_location)
            / total
            * 100:.1f
        }%)"
    )
