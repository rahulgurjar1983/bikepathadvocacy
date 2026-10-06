import hashlib
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlencode

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
PROJECT_CONTACT = "https://github.com/rahulgurjar1983/bikepathadvocacy/issues"
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 0.1
REQUEST_TIMEOUT_SECONDS = 180


class OverpassError(RuntimeError):
    pass


@dataclass(frozen=True)
class ManifestEntry:
    name: str
    path: str
    sha256: str
    bytes: int
    source: str
    request: str
    url: str
    licence: str
    attribution: str
    retrieved_at: str

    def as_dict(self) -> dict[str, str | int]:
        return asdict(self)


class OverpassClient:
    def __init__(self, endpoint: str = OVERPASS_ENDPOINT, contact: str = PROJECT_CONTACT):
        self.endpoint = endpoint
        self.user_agent = f"bikeplan/{version('bikeplan')} (contact: {contact})"

    def fetch(
        self,
        query: str,
        osm_date: str,
        output: str | Path,
        *,
        licence: str,
        attribution: str,
    ) -> ManifestEntry:
        request = self._pin_date(query, osm_date)
        body = urlencode({"data": request}).encode("ascii")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": self.user_agent,
        }
        for attempt in range(MAX_RETRIES + 1):
            http_request = urllib.request.Request(
                self.endpoint, data=body, headers=headers, method="POST"
            )
            try:
                with urllib.request.urlopen(
                    http_request, timeout=REQUEST_TIMEOUT_SECONDS
                ) as response:
                    content = response.read()
                break
            except (urllib.error.URLError, OSError, TimeoutError) as error:
                if isinstance(error, urllib.error.HTTPError):
                    error.close()
                if attempt == MAX_RETRIES:
                    raise OverpassError(str(error)) from error
                time.sleep(RETRY_BASE_SECONDS * 2**attempt)

        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(content)
        return ManifestEntry(
            name=output_path.name,
            path=output_path.as_posix(),
            sha256=hashlib.sha256(content).hexdigest(),
            bytes=len(content),
            source="OpenStreetMap via Overpass",
            request=request,
            url=self.endpoint,
            licence=licence,
            attribution=attribution,
            retrieved_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        )

    @staticmethod
    def _pin_date(query: str, osm_date: str) -> str:
        settings, separator, body = query.partition(";")
        if separator and settings.startswith("["):
            return f'{settings}[date:"{osm_date}"];{body}'
        return f'[date:"{osm_date}"];{query}'
