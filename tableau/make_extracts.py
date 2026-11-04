"""Write each tableau/data/*.csv as a Tableau Hyper extract (schema Extract, table Extract), the form Tableau Public saves."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from tableauhyperapi import Connection, CreateMode, HyperProcess, Inserter, SqlType, TableDefinition, TableName, Telemetry

DATA = Path(__file__).resolve().parent / "data"
DATES = {"scheduled_date"}


def sql_type(col: str, dtype) -> SqlType:
    if col in DATES:
        return SqlType.date()
    if pd.api.types.is_integer_dtype(dtype):
        return SqlType.big_int()
    if pd.api.types.is_float_dtype(dtype):
        return SqlType.double()
    return SqlType.text()


def main() -> None:
    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
        for csv in sorted(DATA.glob("*.csv")):
            df = pd.read_csv(csv)
            for c in DATES & set(df.columns):
                df[c] = pd.to_datetime(df[c]).dt.date
            table = TableDefinition(TableName("Extract", "Extract"),
                                    [TableDefinition.Column(c, sql_type(c, t)) for c, t in df.dtypes.items()])
            out = csv.with_suffix(".hyper")
            with Connection(hp.endpoint, out, CreateMode.CREATE_AND_REPLACE) as con:
                con.catalog.create_schema("Extract")
                con.catalog.create_table(table)
                rows = [[None if pd.isna(v) else v for v in r] for r in df.itertuples(index=False, name=None)]
                with Inserter(con, table) as ins:
                    ins.add_rows(rows)
                    ins.execute()
                n = con.execute_scalar_query("SELECT COUNT(*) FROM \"Extract\".\"Extract\"")
            print(f"{out.name}: {n:,} rows")


if __name__ == "__main__":
    main()
