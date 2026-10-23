import struct
from pathlib import Path

from bikeplan.map_checks import archive_member

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SIZES = {"phone": (390, 844), "desktop": (1440, 900)}


def picture_size(path: Path) -> tuple[int, int] | None:
    blob = path.read_bytes()[:24]
    if len(blob) < 24 or blob[:8] != PNG_SIGNATURE:
        return None
    return struct.unpack(">II", blob[16:24])


def picture_problems(release: Path, name: str) -> list[str]:
    problems = []
    for label, (width, height) in SIZES.items():
        kept = f"{name}-{label}.png"
        if not (release / kept).is_file():
            problems.append(f"{name}: {kept} is not in the release")
            continue
        size = picture_size(release / kept)
        if size is None:
            problems.append(f"{name}: {kept} is not a PNG picture")
        elif size != (width, height):
            problems.append(f"{name}: {kept} is {size[0]} by {size[1]}, not {width} by {height}")
    return problems


def shot_problems(release: Path) -> list[str]:
    archives = sorted(p for p in release.glob("*.tar.gz") if p.name != "artifacts.tar.gz")
    found = [archive for archive in archives if archive_member(archive, "options.json")]
    return [
        problem
        for archive in found
        for problem in picture_problems(release, archive.name.removesuffix(".tar.gz"))
    ]
