import argparse
import os
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

parser = argparse.ArgumentParser(description="Execute SQL templates against Databricks.")
parser.add_argument(
    "--env",
    required=True,
    help="Environment name to substitute into SQL templates (e.g. dev, qa, prod).",
)
args = parser.parse_args()

w = WorkspaceClient(
    host=os.environ["DATABRICKS_HOST"],
    token=os.environ["DATABRICKS_TOKEN"]
)

warehouse_name = os.environ.get(
    "DATABRICKS_WAREHOUSE_NAME",
    "Serverless Starter Warehouse"
)

warehouse = next((wh for wh in w.warehouses.list() if wh.name == warehouse_name), None)
if not warehouse:
    raise ValueError(f"Warehouse '{warehouse_name}' not found")

print(f"Using warehouse: {warehouse.name} ({warehouse.id})")
print(f"Environment: {args.env}")

sql_dir = Path(__file__).parent


def run_sql(statement: str):
    statement = statement.strip()
    if not statement:
        return

    print(f"Running: {statement}")

    response = w.statement_execution.execute_statement(
        statement=statement,
        warehouse_id=warehouse.id,
        wait_timeout="30s"
    )

    if response.status.state != StatementState.SUCCEEDED:
        raise Exception(f"Failed:\n{statement}\n{response.status.error}")

    print("  OK")


for sql_file in sorted(sql_dir.glob("*.sql")):
    print(f"\nExecuting file: {sql_file.name}")

    sql_text = sql_file.read_text()

    # Replace template variables such as {env}
    sql_text = sql_text.format(env=args.env)

    statements = sql_text.split(";")

    for stmt in statements:
        run_sql(stmt)