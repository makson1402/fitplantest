#!/usr/bin/env python3
"""Structural OpenAPI checker: YAML parse, $ref resolution, operationId uniqueness,
path params declared, responses present, x-requirements listed."""
import re, sys, yaml
path = sys.argv[1] if len(sys.argv) > 1 else "docs/api/openapi.yaml"
d = yaml.safe_load(open(path, encoding="utf-8"))
errs = []
def resolve(ref):
    if not ref.startswith("#/"): errs.append(f"external ref {ref}"); return None
    n = d
    for p in ref[2:].split("/"):
        p = p.replace("~1", "/").replace("~0", "~")
        if not isinstance(n, dict) or p not in n: errs.append(f"unresolved {ref}"); return None
        n = n[p]
    return n
used = set()
def walk(n):
    if isinstance(n, dict):
        if "$ref" in n:
            used.add(n["$ref"]); resolve(n["$ref"])
        for v in n.values(): walk(v)
    elif isinstance(n, list):
        for v in n: walk(v)
walk(d)
ops, reqs = {}, set()
for p, item in d["paths"].items():
    pparams = {resolve(x["$ref"]).get("name") if "$ref" in x else x["name"] for x in item.get("parameters", [])}
    for m, op in item.items():
        if m not in ("get","post","put","patch","delete"): continue
        oid = op.get("operationId")
        if not oid: errs.append(f"{m} {p}: no operationId")
        elif oid in ops: errs.append(f"dup operationId {oid}")
        ops[oid] = (m, p)
        names = set(pparams)
        for x in op.get("parameters", []):
            x = resolve(x["$ref"]) if "$ref" in x else x
            if x: names.add(x["name"])
        for t in re.findall(r"\{(\w+)\}", p):
            if t not in names: errs.append(f"{oid}: path param {t} undeclared")
        if not op.get("responses"): errs.append(f"{oid}: no responses")
        xr = op.get("x-requirements")
        if not xr and oid != "getHealth": errs.append(f"{oid}: no x-requirements")
        elif xr: reqs.update(xr)
        if m in ("post","put","patch") and "requestBody" not in op and not oid.startswith(("logout","trigger")):
            pass
unused = [k for k in d["components"].get("schemas", {}) if f"#/components/schemas/{k}" not in used]
print(f"operations={len(ops)} requirements_covered={len(reqs)}")
print("unused schemas:", unused)
print("reqs:", " ".join(sorted(reqs)))
print("ERRORS:" if errs else "OK", *errs, sep="\n")
sys.exit(1 if errs else 0)
