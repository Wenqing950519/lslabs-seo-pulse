"""One JSON line per hosted tool call or sign-in, written to stderr.

Cloud Run forwards JSON lines on stderr to Cloud Logging as jsonPayload (with
`severity` and `message` recognised), so monitoring can count tools, failures,
limit hits and cache hits with log-based metrics. Records never carry tool
arguments, emails or tokens; callers appear only as a salted 12-character hash
of their Google `sub`, enough to count distinct users. See docs/monitoring.md.
"""
import hashlib
import json
import sys


def write(line):
    print(line, file=sys.stderr, flush=True)


def subject_hash(subject):
    return hashlib.sha256(f"seo-pulse|{subject}".encode()).hexdigest()[:12]


def emit(event, severity="INFO", **fields):
    record = {"severity": severity, "message": f"seo_pulse.{event}", "event": event, **fields}
    write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
