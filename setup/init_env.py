# setup/init_catalog.py
import os
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

w = WorkspaceClient(
    host=os.environ["DATABRICKS_HOST"],
    token=os.environ["DATABRICKS_TOKEN"]
)

warehouse_id = os.environ["DATABRICKS_WAREHOUSE_ID"]

statements = [
    "CREATE CATALOG IF NOT EXISTS osrs_dev",
    "CREATE CATALOG IF NOT EXISTS osrs_prod",
]

for sql in statements:
    print(f"Running: {sql}")
    response = w.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=warehouse_id,
        wait_timeout="30s"
    )
    if response.status.state != StatementState.SUCCEEDED:
        raise Exception(f"Failed: {sql}\n{response.status.error}")
    print(f"  OK")