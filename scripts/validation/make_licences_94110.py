"""Build the ARM 94110 licence file: the as-of licence files whose zip is 94110, plus the files with no zip that
place into 94110. A file with no zip gets one, in this order: (1) a file of licences_asof.json with a zip at the same
normalised address; (2) ABC's export table (abc_export_sf) at the same premises address; (3) a registered business
at the same street address (its address carries a zip); (4) the majority zip of the 5 nearest files with a zip
(by map point). A file with no zip, no address match and no map point is left unplaced (not 94110)."""
import collections, json, math, os, re, subprocess, sys
SRC = os.path.join(os.environ.get("LOCAL_DATA_DIR", os.path.expanduser("~/sfhp-local")), "backtest", "licences_asof.json")
OUT = sys.argv[1]
DB = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres@localhost:55433/sfhp_local")
d = json.load(open(SRC))
fs = d["files"]
def norm(a): return re.sub(r"\s+", " ", (a or "").upper().split(",")[0]).strip()
def q(sql):
    out = subprocess.run(["psql", DB, "-At", "-F", "\t", "-c", sql], capture_output=True, text=True, check=True).stdout
    return [l.split("\t") for l in out.splitlines() if l]
by_addr = collections.defaultdict(collections.Counter)
for f in fs:
    if f.get("zip"):
        by_addr[norm(f.get("normalized_address") or f["address"])][f["zip"]] += 1
exp = collections.defaultdict(collections.Counter)
for a, z in q("select prem_addr_1, prem_zip from abc_export_sf where prem_zip is not null"):
    exp[norm(a)][z[:5]] += 1
bus = collections.defaultdict(collections.Counter)
for (a,) in q("select address from businesses where address ~ 'CA 9[0-9]{4}'"):
    m = re.search(r"CA (9\d{4})", a)
    bus[norm(a)][m.group(1)] += 1
zipped = [(f["lat"], f["lng"], f["zip"]) for f in fs if f.get("zip") and f.get("lat") is not None]
def hav(a, b, c, e):
    p1, p2 = math.radians(a), math.radians(c); dp = p2 - p1; dl = math.radians(e - b)
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*6371008.8*math.asin(math.sqrt(h))
how = collections.Counter(); keep = []; decided = []
for f in fs:
    z, basis = f.get("zip") or "", "zip"
    if not z:
        k = norm(f.get("normalized_address") or f.get("address"))
        for name, table in (("same address, licence file", by_addr), ("same address, ABC export", exp), ("same address, registered business", bus)):
            if k and table.get(k):
                z, basis = table[k].most_common(1)[0][0], name; break
        if not z and f.get("lat") is not None:
            near = sorted(zipped, key=lambda t: hav(f["lat"], f["lng"], t[0], t[1]))[:5]
            votes = collections.Counter(t[2] for t in near)
            z, n = votes.most_common(1)[0]
            basis = f"nearest 5 licence files ({n}/5 agree)"
            if "94110" in votes and z != "94110" or (z == "94110" and n < 5):
                basis += ", near the 94110 edge"
        if not z:
            basis = "unplaced"
        how[(basis.split(" (")[0] if basis.startswith("nearest") else basis)] += 1
        decided.append({"file_number": f["file_number"], "address": f.get("address"), "zip": z, "basis": basis})
    if z == "94110":
        keep.append(f)
out = dict(d)
out["files"] = keep
out["_arm"] = ("ARM 94110: the files of licences_asof.json whose zip is 94110, plus the files with no zip placed in "
               "94110 (" + __doc__.split("(1)")[1].strip() + ")")
out["counts"] = {"files": len(keep), "with_zip_94110": sum(1 for f in keep if f.get("zip") == "94110"),
                 "no_zip_placed_94110": sum(1 for f in keep if not f.get("zip"))}
json.dump(out, open(OUT, "w"), indent=0)
json.dump(decided, open(OUT.replace(".json", "-nozip-decisions.json"), "w"), indent=1)
print(out["counts"]); print(dict(how))
edge = [x for x in decided if "edge" in x["basis"]]
print("no-zip files near the 94110 edge:", len(edge), "of which placed in 94110:", sum(1 for x in edge if x["zip"] == "94110"))
print("no-zip placed in 94110 by basis:", collections.Counter(x["basis"].split(" (")[0] for x in decided if x["zip"] == "94110"))
