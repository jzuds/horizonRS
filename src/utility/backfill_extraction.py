import subprocess
from datetime import datetime, timedelta
import argparse


def run_range(start_date, end_date, landing_root, script_path, stop_on_error=False):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")

        cmd = [
            "python",
            script_path,
            "--landing-root", landing_root,
            "--date", date_str
        ]

        print(f"Running for {date_str}...")
        result = subprocess.run(cmd)

        if result.returncode != 0:
            print(f"❌ Failed for {date_str}")
            if stop_on_error:
                break

        current += timedelta(days=1)

    print("Done.")


def main():
    parser = argparse.ArgumentParser(
        description="Run ge_price_data_24h.py over a range of dates"
    )

    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--landing-root",
        default="./output/ge_price_24h",
        help="Landing root directory"
    )
    parser.add_argument(
        "--script-path",
        default="src/extract/ge_price_data_24h.py",
        help="Path to the target script"
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop execution if a date fails"
    )

    args = parser.parse_args()

    run_range(
        args.start_date,
        args.end_date,
        args.landing_root,
        args.script_path,
        args.stop_on_error
    )


if __name__ == "__main__":
    main()