#!/usr/bin/env python3
"""Generate a Mermaid ERD from a live PostgreSQL database that has schema_postgres.sql applied.
Usage: python3 scripts/gen_erd.py "<psql args, e.g. -h /tmp/pgsock -U postgres -d fp2>" > erd.mmd"""
import subprocess, sys, shlex
args = shlex.split(sys.argv[1])
def q(sql):
    out = subprocess.run(["psql", *args, "-At", "-F", "|", "-c", sql], capture_output=True, text=True, check=True).stdout
    return [l.split("|") for l in out.splitlines() if l]
cols = q("""select c.table_name, c.column_name, c.data_type, c.udt_name,
 exists(select 1 from information_schema.key_column_usage k join information_schema.table_constraints t
   on t.constraint_name=k.constraint_name and t.table_schema=k.table_schema
   where t.constraint_type='PRIMARY KEY' and k.table_name=c.table_name and k.column_name=c.column_name and k.table_schema='public')
 from information_schema.columns c join information_schema.tables t using(table_schema,table_name)
 where c.table_schema='public' and t.table_type='BASE TABLE' order by c.table_name, c.ordinal_position""")
fks = q("""select tc.table_name, kcu.column_name, ccu.table_name from information_schema.table_constraints tc
 join information_schema.key_column_usage kcu using(constraint_name, table_schema)
 join information_schema.constraint_column_usage ccu using(constraint_name, table_schema)
 where tc.constraint_type='FOREIGN KEY' and tc.table_schema='public' order by 1,2""")
print("erDiagram")
for t in dict.fromkeys(c[0] for c in cols):
    print(f"  {t} {{")
    for c in cols:
        if c[0] == t:
            ty = (c[3] if c[2] == "USER-DEFINED" else c[2]).replace(" ", "_")
            print(f"    {ty} {c[1]}{' PK' if c[4]=='t' else ''}")
    print("  }")
for t, col, ref in fks:
    print(f"  {ref} ||--o{{ {t} : \"{col}\"")
