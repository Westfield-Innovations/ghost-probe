# ghost_probe.py
#
# GHOST PROBE READER
# Created by Carl D. Hildebrandt · Westfield Innovations LLC
# © 2026 Westfield Innovations LLC
# The Ghost Probe and its terms of use are published at OFFICIAL_ADDRESS below.

"""Ghost Probe reader.

The Ghost Probe's words are kept at one official address by Westfield
Innovations. This file is the reader. Each time your program uses it, it
reads the current words from that address and hands them to your program.

Everything this file does:
  1. Makes one read-only request to the official address.
  2. Puts those words together with your subject and boundary, for your own AI.
  3. Puts the creator lines at the end of every report.

What this file never does:
  - It holds none of the Ghost Probe's words. They live at the official address.
  - It sends nothing about you or your subject to Westfield. The request
    carries no subject, no account and no identifier.
  - It writes nothing to your disk.
  - It contacts no address except the official one.

Install it with `pip install ghost-probe`, or copy this one file.

Use it from your own program:

    import ghost_probe

    def my_ai(text):
        # Send `text` to the AI you already use and return its answer.
        ...

    report = ghost_probe.run(
        subject="...the word, label or cause under test...",
        boundary="...the domain: what is in scope, and what is not...",
        ask=my_ai,
    )

Or run this file by itself to see exactly what it reads:

    python ghost_probe.py

This file needs nothing installed beyond Python itself.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from typing import Callable, Dict, Optional, Tuple

__version__ = "1.0.0"

__all__ = [
    "OFFICIAL_ADDRESS",
    "CREATOR_LINE",
    "TOOL",
    "GhostProbeUnavailable",
    "Publication",
    "read",
    "words",
    "credit",
    "prompt",
    "run",
]

# ---------------------------------------------------------------------------
# The one address this file reads. Westfield sets it once.
# ---------------------------------------------------------------------------
OFFICIAL_ADDRESS = "https://azus.ai/tools/ghost-probe/"

# The fixed origin line. It travels inside this file, so it is present even
# when the official address cannot be reached.
CREATOR_LINE = "Created by Carl D. Hildebrandt · Westfield Innovations LLC"

# The name the publication carries. An answer under any other name is not it.
TOOL = "Ghost Probe"

# How long one read is held in memory before the address is read again.
# Held in memory only. Nothing is ever written to disk.
HOLD_SECONDS = 300

# How long to wait for the official address, and the most it may send back.
TIMEOUT_SECONDS = 15
MAX_BYTES = 2_000_000

# Plain http is accepted only for this same machine, so the Westfield team can
# try the reader against a stand-in source before the official page is live.
_THIS_MACHINE = ("127.0.0.1", "localhost", "::1")

_EDITION_NAME = re.compile(r"^[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*$")


class GhostProbeUnavailable(RuntimeError):
    """The official Ghost Probe could not be read. Nothing was run."""


@dataclass(frozen=True)
class Publication:
    """One reading of the official Ghost Probe. Lives in memory only."""

    tool: str
    edition: str
    issued: str
    words: str
    official_address: str
    toolbox_address: str
    connections: Tuple[Tuple[str, str], ...]
    tools: Tuple[Tuple[str, str], ...]
    terms: str
    read_from: str
    # Where the title block (addresses, connections, tools, terms) was read.
    # For one fixed edition it is the current file, so the credit stays current.
    title_read_from: str = ""

    def credit(self) -> str:
        """The lines that close every report."""
        return "\n".join(
            [
                CREATOR_LINE,
                "Official {0}: {1}".format(self.tool, self.official_address),
                "Edition used: {0}".format(self.edition),
                "More Westfield tools: {0}".format(self.toolbox_address),
            ]
        )


# ---------------------------------------------------------------------------
# Reading the official address. This is the only network code in the file.
# ---------------------------------------------------------------------------

def _place(address: str) -> Tuple[str, str, int]:
    """Scheme, host and port of an address, for comparing two addresses."""
    parts = urllib.parse.urlsplit(address)
    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").lower()
    port = parts.port or (443 if scheme == "https" else 80)
    return scheme, host, port


def _official_base() -> str:
    base = str(OFFICIAL_ADDRESS).strip()
    if not base.endswith("/"):
        base += "/"
    scheme, host, _port = _place(base)
    if host and scheme == "https":
        return base
    if host and scheme == "http" and host in _THIS_MACHINE:
        return base
    raise GhostProbeUnavailable(
        "The official address must begin with https://. "
        "It is set to: {0!r}. Nothing was read and nothing was run.".format(OFFICIAL_ADDRESS)
    )


def _address_for(edition: Optional[str]) -> str:
    """The address of the current edition, or of one fixed edition."""
    base = _official_base()
    if edition is None:
        return base + "source.json"
    name = str(edition).strip()
    if not _EDITION_NAME.match(name):
        raise ValueError(
            "An edition is named by its number, such as 3. Got: {0!r}".format(edition)
        )
    return base + "editions/" + name + "/source.json"


class _StayAtTheOfficialAddress(urllib.request.HTTPRedirectHandler):
    """Refuse to be sent anywhere other than the official address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _place(newurl) != _place(req.full_url):
            raise GhostProbeUnavailable(
                "The official address tried to send this reader to a different "
                "place ({0}). The reader stays at the official address, so "
                "nothing was read and nothing was run.".format(newurl)
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _cannot_read(address: str, why: str) -> str:
    return (
        "The official Ghost Probe could not be read from {0} ({1}). "
        "Nothing was run. Open {2} in a browser to check the publication."
    ).format(address, why, _official_base())


def _fetch(address: str) -> bytes:
    """One read-only request. No subject, no account, no identifier."""
    request = urllib.request.Request(
        address,
        method="GET",
        headers={
            "User-Agent": "ghost-probe-reader/" + __version__,
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        },
    )
    opener = urllib.request.build_opener(_StayAtTheOfficialAddress())
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            if _place(response.geturl()) != _place(address):
                raise GhostProbeUnavailable(
                    _cannot_read(address, "the answer came from a different place")
                )
            raw = response.read(MAX_BYTES + 1)
    except GhostProbeUnavailable:
        raise
    except urllib.error.HTTPError as problem:
        raise GhostProbeUnavailable(
            _cannot_read(address, "the address answered {0}".format(problem.code))
        ) from None
    except (urllib.error.URLError, OSError, ValueError) as problem:
        reason = getattr(problem, "reason", problem)
        raise GhostProbeUnavailable(
            _cannot_read(address, "no answer: {0}".format(reason))
        ) from None
    if len(raw) > MAX_BYTES:
        raise GhostProbeUnavailable(
            _cannot_read(address, "the answer was larger than expected")
        )
    return raw


def _text(data: dict, key: str, address: str) -> str:
    value = data.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise GhostProbeUnavailable(
        _cannot_read(address, "the publication is missing its {0!r}".format(key))
    )


def _pairs(data: dict, key: str, first: str, second: str) -> Tuple[Tuple[str, str], ...]:
    found = []
    for item in data.get(key) or []:
        if isinstance(item, dict):
            a = str(item.get(first) or "").strip()
            b = str(item.get(second) or "").strip()
            if a and b:
                found.append((a, b))
    return tuple(found)


def _not_the_publication(address: str) -> GhostProbeUnavailable:
    return GhostProbeUnavailable(
        _cannot_read(address, "the answer is not the Ghost Probe publication")
    )


def _terms(data: dict, address: str) -> str:
    """The terms of use, one per line. A publication always carries them."""
    found = data.get("terms")
    if isinstance(found, list) and all(isinstance(line, str) for line in found):
        found = "\n".join(line.strip() for line in found if line.strip())
    if isinstance(found, str) and found.strip():
        return found.strip()
    raise _not_the_publication(address)


def _publication(raw: bytes, address: str, edition: Optional[str] = None) -> Publication:
    """The publication in an answer. edition, when given, is the one asked for."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _not_the_publication(address) from None
    if not isinstance(data, dict):
        raise _not_the_publication(address)
    publication = Publication(
        tool=_text(data, "tool", address),
        edition=_text(data, "edition", address),
        issued=_text(data, "issued", address),
        words=_text(data, "words", address),
        official_address=_text(data, "official_address", address),
        toolbox_address=_text(data, "toolbox_address", address),
        connections=_pairs(data, "connections", "label", "address"),
        tools=_pairs(data, "tools", "name", "address"),
        terms=_terms(data, address),
        read_from=address,
    )
    if publication.tool != TOOL:
        raise _not_the_publication(address)
    if edition is not None and publication.edition != edition:
        raise _not_the_publication(address)
    return publication


# One reading is held in memory for HOLD_SECONDS, then read again.
_held: Dict[str, Tuple[float, Publication]] = {}
_held_lock = threading.Lock()


def _held_reading(address: str, edition: Optional[str], fresh: bool) -> Publication:
    """One address, read again only after HOLD_SECONDS or when fresh."""
    now = time.monotonic()
    with _held_lock:
        kept = _held.get(address)
        if kept and not fresh and now - kept[0] < HOLD_SECONDS:
            return kept[1]
    publication = _publication(_fetch(address), address, edition)
    with _held_lock:
        _held[address] = (now, publication)
    return publication


def read(edition: Optional[str] = None, fresh: bool = False) -> Publication:
    """Read the official Ghost Probe.

    edition=None reads the current edition. edition="3" (or 3) reads
    edition 3, whose words never change once Westfield has published it.
    The title block (the addresses, connections, tools and terms) always
    comes from the current file, so a changed link reaches a program fixed
    to an edition too.
    fresh=True reads the address again now instead of using the reading
    held in memory.
    """
    fixed = None if edition is None else _address_for(edition)
    current = _held_reading(_address_for(None), None, fresh)
    if fixed is None:
        return replace(current, title_read_from=current.read_from)
    words = _held_reading(fixed, str(edition).strip(), fresh)
    return replace(
        words,
        official_address=current.official_address,
        toolbox_address=current.toolbox_address,
        connections=current.connections,
        tools=current.tools,
        terms=current.terms,
        title_read_from=current.read_from,
    )


# ---------------------------------------------------------------------------
# What your program calls.
# ---------------------------------------------------------------------------

def words(edition: Optional[str] = None) -> str:
    """The Ghost Probe's words, as read from the official address just now."""
    return read(edition).words


def credit(edition: Optional[str] = None) -> str:
    """The lines that close every report."""
    return read(edition).credit()


def _declared(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "The Ghost Probe needs a declared {0} before it runs. None was given.".format(name)
        )
    return value.strip()


def _put_together(publication: Publication, subject: str, boundary: str) -> str:
    subject = _declared("subject", subject)
    boundary = _declared("boundary", boundary)
    return "\n".join(
        [
            publication.words,
            "",
            "SUBJECT UNDER TEST: " + subject,
            "BOUNDARY: " + boundary,
        ]
    )


def prompt(subject: str, boundary: str, edition: Optional[str] = None) -> str:
    """The official words with your subject and boundary, ready to give to
    your own AI. Use this if you would rather send it yourself."""
    return _put_together(read(edition), subject, boundary)


def _with_credit(report: str, publication: Publication) -> str:
    """The report with all four credit lines at its end.

    A report is left as it is only when its last four non-blank lines are the
    four credit lines, in order and exactly. Otherwise the four lines are
    added, even if that repeats some of them: a repeated line is better than
    a missing one.
    """
    credit_lines = publication.credit().splitlines()
    last_lines = [line for line in report.splitlines() if line.strip()][-len(credit_lines):]
    if last_lines == credit_lines:
        return report
    return report.rstrip() + "\n\n" + publication.credit() + "\n"


def run(
    subject: str,
    boundary: str,
    ask: Callable[[str], str],
    edition: Optional[str] = None,
) -> str:
    """Run the Ghost Probe on your subject with your own AI.

    `ask` is any function of yours that takes text and returns your AI's
    answer. Your subject goes only where your function sends it.
    The report comes back with the creator lines at the end.
    """
    if not callable(ask):
        raise TypeError("`ask` must be a function that takes text and returns your AI's answer.")
    publication = read(edition)
    question = _put_together(publication, subject, boundary)
    answer = ask(question)
    if not isinstance(answer, str):
        raise TypeError("`ask` must return your AI's answer as text.")
    return _with_credit(answer, publication)


# ---------------------------------------------------------------------------
# Run this file by itself to see what it reads.
# ---------------------------------------------------------------------------

def _status(publication: Publication) -> str:
    lines = [
        "GHOST PROBE READER  (reader version {0})".format(__version__),
        CREATOR_LINE,
        "",
        "Read from:         {0}".format(publication.read_from),
    ]
    if publication.title_read_from and publication.title_read_from != publication.read_from:
        lines.append("Title block from:  {0}".format(publication.title_read_from))
    lines += [
        "Tool:              {0}".format(publication.tool),
        "Edition:           {0}  (issued {1})".format(publication.edition, publication.issued),
    ]
    lines.append("Official address:  {0}".format(publication.official_address))
    lines.append("More tools:        {0}".format(publication.toolbox_address))
    if publication.tools:
        lines.append("Westfield tools:")
        lines.extend("  {0}: {1}".format(name, where) for name, where in publication.tools)
    if publication.connections:
        lines.append("Connections:")
        lines.extend("  {0}: {1}".format(label, where) for label, where in publication.connections)
    if publication.terms:
        lines.append("Terms of use:")
        lines.extend("  " + line for line in publication.terms.splitlines())
    two = publication.title_read_from not in ("", publication.read_from)
    lines.extend(
        [
            "",
            "This reader made two read-only requests, to the addresses above."
            if two
            else "This reader made one read-only request, to the address above.",
            "It sent no subject, no account and no identifier, and it wrote nothing to disk.",
            "The Ghost Probe's words were read ({0:,} characters). They are held in memory "
            "only and are not saved.".format(len(publication.words)),
        ]
    )
    return "\n".join(lines)


def main(arguments=None) -> int:
    parser = argparse.ArgumentParser(
        prog="ghost_probe.py",
        description="Read the official Ghost Probe and show what was read.",
    )
    parser.add_argument(
        "--edition",
        default=None,
        help="read one fixed edition by its number instead of the current one",
    )
    chosen = parser.parse_args(arguments)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        publication = read(chosen.edition, fresh=True)
    except (GhostProbeUnavailable, ValueError) as problem:
        print(CREATOR_LINE, file=sys.stderr)
        print(str(problem), file=sys.stderr)
        return 1
    print(_status(publication))
    return 0


if __name__ == "__main__":
    sys.exit(main())

