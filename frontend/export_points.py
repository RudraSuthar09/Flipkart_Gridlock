import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "processed_dataset_cleaned.csv"
OUTPUT = ROOT / "frontend" / "public" / "data" / "points.json"


VIOLATION_COLUMNS = [
    "PARKING NEAR ROAD CROSSING--104",
    "PARKING ON FOOTPATH--105",
    "PARKING NEAR TRAFFIC LIGHT OR ZEBRA CROSS--106",
    "PARKING IN A MAIN ROAD--107",
    "PARKING OPPOSITE TO ANOTHER PARKED VEHICLE--108",
    "DOUBLE PARKING--109",
    "FAIL TO USE SAFETY BELTS--110",
    "PARKING NEAR BUSTOP/SCHOOL/HOSPITAL ETC--111",
    "WRONG PARKING--112",
    "NO PARKING--113",
    "JUMPING TRAFFIC SIGNAL--115",
    "DEFECTIVE NUMBER PLATE--116",
    "CARRYING LENGHTY MATERIAL--123",
    "REFUSE TO GO FOR HIRE--124",
    "DEMANDING EXCESS FARE--125",
    "VIOLATING LANE DISIPLINE--130",
    "USING BLACK FILM/OTHER MATERIALS--133",
    "U TURN PROHIBITED--134",
    "AGAINST ONE WAY/NO ENTRY--135",
    "OBSTRUCTING DRIVER--136",
    "PARKING OTHER THAN BUS STOP--139",
    "RIDER NOT WEARING HELMET--140",
    "WITHOUT SIDE MIRROR--144",
    "STOPING ON WHITE/STOP LINE--146",
    "H T V PROHIBITED--147",
    "2W/3W - USING MOBILE PHONE--237",
    "OTHER - USING MOBILE PHONE--437",
]


def as_int(value):
    if value in ("", None):
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def as_float(value):
    if value in ("", None):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def clean_text(value):
    return (value or "").strip()


def violation_name(row):
    for column in VIOLATION_COLUMNS:
        if as_int(row.get(column)) == 1:
            return column
    return "Traffic violation"


def main():
    points = []

    with INPUT.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        for row in reader:
            lat = as_float(row.get("latitude"))
            lng = as_float(row.get("longitude"))
            year = as_int(row.get("created_year"))
            month = as_int(row.get("created_month"))
            day = as_int(row.get("created_day"))
            hour = as_int(row.get("created_hour"))

            if None in (lat, lng, year, month, day, hour):
                continue

            minute = as_int(row.get("created_minute")) or 0
            second = as_int(row.get("created_second")) or 0

            points.append(
                {
                    "lat": lat,
                    "lng": lng,
                    "year": year,
                    "month": month,
                    "day": day,
                    "hour": hour,
                    "date_label": f"{year:04d}-{month:02d}-{day:02d}",
                    "time_label": f"{hour:02d}:{minute:02d}:{second:02d}",
                    "area": clean_text(row.get("area")),
                    "pincode": clean_text(row.get("pincode")).removesuffix(".0"),
                    "police_station": clean_text(row.get("police_station")),
                    "violation": violation_name(row),
                }
            )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as target:
        json.dump(points, target, separators=(",", ":"))

    print(f"Wrote {len(points)} points to {OUTPUT}")


if __name__ == "__main__":
    main()
