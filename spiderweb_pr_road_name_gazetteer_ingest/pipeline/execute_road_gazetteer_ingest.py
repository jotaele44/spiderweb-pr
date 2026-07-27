#!/usr/bin/env python3
from pathlib import Path
from road_gazetteer_ingest import RoadGazetteerIngest

if __name__ == '__main__':
    RoadGazetteerIngest(
        source_root=Path('data/reference/roads/raw'),
        gnis_dir=Path('data/reference/gazetteer/processed'),
        output_dir=Path('data/reference/roads/processed'),
    ).run()
