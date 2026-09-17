import hashlib, re, shutil, urllib.request, zipfile
from pathlib import Path

BASE = "https://download.blender.org/release/Blender4.5/"
tools = Path(r"d:\python_project\Wisdom_Computing_Perspective\achievement-holo-cards\tools")
tools.mkdir(parents=True, exist_ok=True)
suffix = "windows-x64.zip"
req = urllib.request.Request(BASE, headers={"User-Agent": "Holo-Card-Studio/1.0"})
listing = urllib.request.urlopen(req, timeout=60).read().decode("utf8")
found = set(re.findall(r"blender-(4\.5\.\d+)-" + re.escape(suffix), listing))
print("found", sorted(found))
version = max(found, key=lambda v: tuple(map(int, v.split("."))))
name = f"blender-{version}-{suffix}"
print("using", name)
checksum_name = f"blender-{version}.sha256"
checksum_path = tools / checksum_name
req = urllib.request.Request(BASE + checksum_name, headers={"User-Agent": "Holo-Card-Studio/1.0"})
with urllib.request.urlopen(req, timeout=90) as r, checksum_path.open("wb") as out:
    shutil.copyfileobj(r, out)
entries = [l.split() for l in checksum_path.read_text().splitlines()]
hashes = [row[0].lower() for row in entries if len(row) > 1 and row[-1].lstrip("*") == name]
assert len(hashes) == 1, hashes
expected = hashes[0]
package = tools / name


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as data:
        for part in iter(lambda: data.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


if package.exists() and digest(package) == expected:
    print("package already ok")
else:
    partial = package.with_suffix(package.suffix + ".part")
    print("downloading", BASE + name)
    req = urllib.request.Request(BASE + name, headers={"User-Agent": "Holo-Card-Studio/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r, partial.open("wb") as out:
        shutil.copyfileobj(r, out)
    got = digest(partial)
    if got != expected:
        raise SystemExit(f"sha mismatch {got} != {expected}")
    partial.replace(package)
    print("download complete", package.stat().st_size)

print("extracting...")
with zipfile.ZipFile(package) as z:
    z.extractall(tools)
exes = list(tools.glob("blender*/blender.exe"))
print("exe", exes)
