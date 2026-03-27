import argparse
import pyarrow.parquet as pq
import pandas as pd
import os
import sys


def inspect_parquet(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found -> {file_path}")
        sys.exit(1)

    print(f"\nInspecting: {file_path}\n")

    parquet_file = pq.ParquetFile(file_path)

    # ---- File-level metadata ----
    print("=== File Metadata ===")
    print(f"Number of rows: {parquet_file.metadata.num_rows}")
    print(f"Number of row groups: {parquet_file.metadata.num_row_groups}")
    print(f"Number of columns: {parquet_file.metadata.num_columns}")
    print(f"Created by: {parquet_file.metadata.created_by}")

    # ---- Schema ----
    print("\n=== Schema ===")
    print(parquet_file.schema)

    # ---- Row group details ----
    print("\n=== Row Group Details ===")
    for i in range(parquet_file.metadata.num_row_groups):
        row_group = parquet_file.metadata.row_group(i)
        print(f"\nRow Group {i}:")
        print(f"  Rows: {row_group.num_rows}")
        print(f"  Total Byte Size: {row_group.total_byte_size}")

        for j in range(row_group.num_columns):
            col = row_group.column(j)
            print(f"    Column: {col.path_in_schema}")
            print(f"      Compression: {col.compression}")
            print(f"      Encodings: {col.encodings}")
            print(f"      Size (compressed): {col.total_compressed_size}")
            print(f"      Size (uncompressed): {col.total_uncompressed_size}")
            print(f"      Has statistics: {col.statistics is not None}")

            if col.statistics:
                stats = col.statistics
                print(f"        Min: {stats.min}")
                print(f"        Max: {stats.max}")
                print(f"        Null count: {stats.null_count}")

    # ---- Column-level summary via pandas ----
    print("\n=== Column Summary (via pandas) ===")
    df = pd.read_parquet(file_path)
    print(df.info())

    print("\nBasic stats:")
    print(df.describe(include='all'))


def main():
    parser = argparse.ArgumentParser(
        description="Inspect a Parquet file and print detailed metadata."
    )
    parser.add_argument(
        "--file",
        help="Path to the Parquet file"
    )

    args = parser.parse_args()
    inspect_parquet(args.file)


if __name__ == "__main__":
    main()