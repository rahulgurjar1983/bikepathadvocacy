from collections.abc import Mapping

CALLER_PREFIXES = (
    "RALPH_",
    "GATE_",
    "NOTIFY_",
    "WAIT_CI_",
    "SHIP_PR_",
    "BIKEPLAN_",
    "REDGREEN_",
    "GITLEAKS_",
    "FAKE_",
)


def caller_settings(environ: Mapping[str, str]) -> list[str]:
    return sorted(name for name in environ if name.startswith(CALLER_PREFIXES))
