from spiderweb.ingest.gpkg_loader import GPKGLoader


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Spiderweb CLI")
    parser.add_argument("--gpkg", required=True, help="Path to GeoPackage")

    args = parser.parse_args()

    loader = GPKGLoader(args.gpkg)
    print("Detected layers:")
    for layer in loader.list_layers():
        print(f" - {layer}")
