import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from bikeplan.config import ConfigError
from bikeplan.snapshot import ManifestEntry, read_url, timestamp


def capture_source(url: str, out: str, licence: str, credit: str) -> Path:
    private = Path.cwd() / "data/private"
    target = Path(out).absolute()
    if not target.is_relative_to(private) or not target.resolve().is_relative_to(private):
        raise ConfigError("Review sources must stay under data/private")
    if target.exists():
        raise ConfigError(f"{target}: already exists; use a new capture folder")
    if urlsplit(url).scheme not in {"http", "https"}:
        raise ConfigError("Review source URL must use http or https")
    if not licence.strip() or not credit.strip():
        raise ConfigError("Review source needs a licence and credit")
    content = read_url(url)
    entry = ManifestEntry(
        name="Review source",
        path="source",
        sha256=hashlib.sha256(content).hexdigest(),
        bytes=len(content),
        source="Plan author",
        request="GET",
        url=url,
        licence=licence,
        attribution=credit,
        retrieved_at=timestamp(),
    )
    target.mkdir(parents=True)
    (target / "source").write_bytes(content)
    (target / "source-manifest.json").write_text(
        json.dumps(entry.as_dict(), indent=2, sort_keys=True) + "\n"
    )
    (target / "review.yaml").write_text("public: false\n")
    return target
