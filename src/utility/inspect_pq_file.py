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

    metadata = parquet_file.metadata

    # ---- File-level metadata ----
    print("=== File Metadata ===")
    print(f"Number of rows: {metadata.num_rows}")
    print(f"Number of row groups: {metadata.num_row_groups}")
    print(f"Number of columns: {metadata.num_columns}")
    print(f"Created by: {metadata.created_by}")

    # ---- Key/value metadata ----
    print("\n=== Key Value Metadata ===")

    if metadata.metadata:
        for key, value in metadata.metadata.items():
            print(
                f"{key.decode('utf-8')}: "
                f"{value.decode('utf-8')}"
            )
    else:
        print("No key/value metadata found.")

    # ---- Schema ----
    print("\n=== Schema ===")
    print(parquet_file.schema)

    # ---- Arrow schema metadata ----
    print("\n=== Arrow Schema Metadata ===")

    arrow_schema = parquet_file.schema_arrow

    if arrow_schema.metadata:
        for key, value in arrow_schema.metadata.items():
            print(
                f"{key.decode('utf-8')}: "
                f"{value.decode('utf-8')}"
            )
    else:
        print("No Arrow schema metadata found.")

    # ---- Row group details ----
    print("\n=== Row Group Details ===")

    for i in range(metadata.num_row_groups):
        row_group = metadata.row_group(i)

        print(f"\nRow Group {i}:")
        print(f"  Rows: {row_group.num_rows}")
        print(f"  Total Byte Size: {row_group.total_byte_size}")

        for j in range(row_group.num_columns):
            col = row_group.column(j)

            print(f"    Column: {col.path_in_schema}")
            print(f"      Compression: {col.compression}")
            print(f"      Encodings: {col.encodings}")
            print(
                f"      Size (compressed): "
                f"{col.total_compressed_size}"
            )
            print(
                f"      Size (uncompressed): "
                f"{col.total_uncompressed_size}"
            )
            print(
                f"      Has statistics: "
                f"{col.statistics is not None}"
            )

            if col.statistics:
                stats = col.statistics

                print(f"        Min: {stats.min}")
                print(f"        Max: {stats.max}")
                print(f"        Null count: {stats.null_count}")

    # ---- Column-level summary via pandas ----
    print("\n=== Column Summary (via pandas) ===")

    df = pd.read_parquet(file_path)

    print(df.info())

    print("\nNull Counts:")
    print(df.isnull().sum())

    print("\nBasic Stats:")
    print("\n=== Numeric Stats ===")
    print(df.describe())

    print("\n=== Datetime Stats ===")

    datetime_cols = df.select_dtypes(
        include=["datetime"]
    ).columns

    if len(datetime_cols) > 0:
        for col in datetime_cols:
            print(f"\n{col}:")
            print(f"  Min: {df[col].min()}")
            print(f"  Max: {df[col].max()}")


def main():
    parser = argparse.ArgumentParser(
        description="Inspect a Parquet file and print detailed metadata."
    )

    parser.add_argument(
        "--file",
        required=True,
        help="Path to the Parquet file",
    )

    args = parser.parse_args()

    inspect_parquet(args.file)


if __name__ == "__main__":
    main()