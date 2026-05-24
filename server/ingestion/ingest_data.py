"""
Data ingestion scripts for PRIIS.

This module contains a CLI for inserting contract records from a CSV
file into the database. The database connection is configured via
SQLAlchemy and reads the connection string from the environment by
default. Use `python ingest_data.py --help` to see usage.
"""

import csv
import argparse
import os
from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.dialects.postgresql import insert


def ingest_contracts(csv_path: str, db_url: str) -> None:
    """Ingest contract records from a CSV file into the database."""
    engine = create_engine(db_url)
    metadata = MetaData(bind=engine)
    contracts_table = Table('contracts', metadata, autoload_with=engine)

    with open(csv_path, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        with engine.begin() as conn:
            for row in reader:
                stmt = insert(contracts_table).values(
                    contract_id=row['contract_id'],
                    vendor_id=int(row['vendor_id']),
                    agency_id=int(row['agency_id']),
                    amount=float(row['amount']),
                    start_date=row['start_date'],
                    end_date=row['end_date'],
                    description=row.get('description', '')
                ).on_conflict_do_nothing(index_elements=['contract_id'])
                conn.execute(stmt)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Ingest contract CSV data into the database.'
    )
    parser.add_argument('csv', help='Path to contract CSV file')
    parser.add_argument(
        '--db',
        default=os.getenv('DATABASE_URL', 'postgresql://user:password@localhost:5432/priis'),
        help='Database URL (default: env DATABASE_URL or local default)',
    )
    args = parser.parse_args()
    ingest_contracts(args.csv, args.db)
    print('Ingestion completed.')


if __name__ == '__main__':
    main()