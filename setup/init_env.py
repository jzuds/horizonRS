# setup/init_catalog.py
import os
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

w = WorkspaceClient(
    host=os.environ["DATABRICKS_HOST"],
    token=os.environ["DATABRICKS_TOKEN"]
)

warehouse_name = os.environ.get("DATABRICKS_WAREHOUSE_NAME", "Serverless Starter Warehouse")
warehouse = next((wh for wh in w.warehouses.list() if wh.name == warehouse_name), None)
if not warehouse:
    raise ValueError(f"Warehouse '{warehouse_name}' not found")

print(f"Using warehouse: {warehouse.name} ({warehouse.id})")

statements = [
    "CREATE CATALOG IF NOT EXISTS osrs_analytics_dev",
    "CREATE CATALOG IF NOT EXISTS osrs_analytics_prod",
]

for sql in statements:
    print(f"Running: {sql}")
    response = w.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=warehouse.id,
        wait_timeout="30s"
    )
    if response.status.state != StatementState.SUCCEEDED:
        raise Exception(f"Failed: {sql}\n{response.status.error}")
    print(f"  OK")