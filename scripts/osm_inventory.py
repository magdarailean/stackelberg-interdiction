import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree


def inventory(path: Path) -> dict:
    classes = Counter()
    direction = Counter()
    tags_present = Counter()
    for _, way in ElementTree.iterparse(path, events=("end",)):
        if way.tag == "node":
            way.clear()
        if way.tag != "way":
            continue
        tags = {tag.get("k"): tag.get("v") for tag in way.findall("tag")}
        road = tags.get("highway")
        if road:
            count = max(0, len(way.findall("nd"))-1)
            classes[road] += count
            direction[tags.get("oneway", "unspecified")] += count
            for name in ("maxspeed", "lanes", "access"):
                if name in tags:
                    tags_present[name] += 1
        way.clear()
    with path.open("rb") as stream:
        fingerprint = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(source=path.name, sha256=fingerprint, road_segments=dict(classes),
                explicit_direction_tags=dict(direction), ways_with_tags=dict(tags_present),
                attribution="© OpenStreetMap contributors when the input is OSM data",
                license_url="https://www.openstreetmap.org/copyright")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("extract", type=Path)
    args = parser.parse_args()
    print(json.dumps(inventory(args.extract), indent=2))
