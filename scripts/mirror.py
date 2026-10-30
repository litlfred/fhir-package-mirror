#!/usr/bin/env python3
"""Mirror FHIR packages from packages.fhir.org (or build.fhir.org for #current) into this repo.

Usage: mirror.py <spec> [<spec> ...]
  spec = name#version, name#current, or name#latest for the newest non-prerelease.

Each package and its transitive dependencies are added as <name>#<version>.tgz
with a SHA512SUMS line, unless already here or on registry.npmjs.org at the
exact version (the seeder reads npm directly). The package's own
package/package.json must match the requested name and version (for #current,
package/package.json version is normalized to "current" so fhir-cache-seed-npm
accepts the tarball as <name>#current.tgz).
Writes mirror-report.txt.
"""
import gzip, hashlib, io, json, re, sys, tarfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ["https://packages.fhir.org", "https://packages2.fhir.org/packages"]
BUILD = "https://build.fhir.org/ig"
NPM = "https://registry.npmjs.org"
report = []
_qas = None


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json, */*"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # retry, then give up
            err = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url}: {err}")


def meta(name):
    for base in REG:
        try:
            return json.loads(get(f"{base}/{name}"))
        except Exception:
            continue
    raise RuntimeError(f"no registry metadata for {name}")


def latest(name):
    vs = [v for v in meta(name).get("versions", {}) if re.fullmatch(r"\d+(\.\d+)*", v)]
    return max(vs, key=lambda v: tuple(int(x) for x in v.split(".")))


def on_npm(name, version):
    if version == "current":
        return False
    try:
        return version in json.loads(get(f"{NPM}/{name}", tries=1)).get("versions", {})
    except Exception:
        return False


def have(name, version):
    return (ROOT / f"{name}#{version}.tgz").exists()


def normalize_current_tgz(raw, name):
    in_tar = tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz")
    out_buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=out_buf, mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as out_tar:
            for member in in_tar.getmembers():
                f = in_tar.extractfile(member) if member.isfile() else None
                if member.name in ("package/package.json", "./package/package.json") and f is not None:
                    pj = json.loads(f.read().decode("utf-8"))
                    if pj.get("name") == name:
                        pj["version"] = "current"
                    new_bytes = (json.dumps(pj, indent=2) + "\n").encode("utf-8")
                    member.size = len(new_bytes)
                    out_tar.addfile(member, io.BytesIO(new_bytes))
                elif f is not None:
                    out_tar.addfile(member, f)
                else:
                    out_tar.addfile(member)
    return out_buf.getvalue()


def fetch(name, version):
    if version == "current":
        global _qas
        if _qas is None:
            _qas = json.loads(get(f"{BUILD}/qas.json"))
        matches = [
            p for p in _qas
            if p.get("package-id") == name and re.search(r"/(master|main)/qa\.json$", p.get("repo", ""))
        ]
        if not matches:
            raise RuntimeError(f"no current build in {BUILD}/qas.json for {name}")
        matches.sort(key=lambda p: p.get("dateISO8601", ""), reverse=True)
        repo_path = matches[0]["repo"][:-8]
        return normalize_current_tgz(get(f"{BUILD}/{repo_path}/package.tgz"), name)
    for base in REG:
        try:
            return get(f"{base}/{name}/{version}")
        except Exception as e:
            last = e
    raise RuntimeError(str(last))


seen = set()


def mirror(name, version):
    if (name, version) in seen:
        return
    seen.add((name, version))
    if re.fullmatch(r"\d+(\.\d+)*\.x", version):
        try:
            pre = version[:-1]
            vs = [v for v in meta(name).get("versions", {})
                  if v.startswith(pre) and re.fullmatch(r"\d+(\.\d+)*", v)]
            v = max(vs, key=lambda v: tuple(int(x) for x in v.split(".")))
            report.append(f"RANGE {name}#{version} = {v}")
            return mirror(name, v)
        except Exception as e:
            report.append(f"FAILED {name}#{version}: cannot resolve range ({e})")
            return
    if version != "current" and not re.fullmatch(r"\d+(\.\d+)*(-[A-Za-z0-9.-]+)?", version):
        report.append(f"SKIPPED {name}#{version}: not a fixed version")
        return
    if have(name, version):
        report.append(f"HAVE {name}#{version}")
        data = (ROOT / f"{name}#{version}.tgz").read_bytes()
    elif on_npm(name, version):
        report.append(f"NPM {name}#{version}")
        return
    else:
        try:
            data = fetch(name, version)
        except Exception as e:
            report.append(f"FAILED {name}#{version}: {e}")
            return
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
        pj = json.load(tf.extractfile("package/package.json"))
    except Exception as e:
        report.append(f"FAILED {name}#{version}: unreadable tarball ({e})")
        return
    if pj.get("name") != name or pj.get("version") != version:
        report.append(f"FAILED {name}#{version}: package.json says {pj.get('name')}#{pj.get('version')}")
        return
    if not have(name, version):
        (ROOT / f"{name}#{version}.tgz").write_bytes(data)
        with open(ROOT / "SHA512SUMS", "a") as f:
            f.write(f"{hashlib.sha512(data).hexdigest()}  {name}#{version}.tgz\n")
        report.append(f"ADDED {name}#{version}")
    for dn, dv in (pj.get("dependencies") or {}).items():
        mirror(dn, dv)


for spec in sys.argv[1:]:
    n, v = spec.split("#", 1)
    if v == "latest":
        try:
            v = latest(n)
            report.append(f"LATEST {n} = {v}")
        except Exception as e:
            report.append(f"FAILED {n}#latest: {e}")
            continue
    mirror(n, v)

(ROOT / "mirror-report.txt").write_text("\n".join(report) + "\n")
print("\n".join(report))
