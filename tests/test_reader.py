"""The reader against a stand-in of the official address."""

from __future__ import annotations

import contextlib
import io
import socket
import unittest
from unittest import mock

import ghost_probe
from tests.standin import StandIn, free_port, publication


class ReaderTestCase(unittest.TestCase):
    """Points the reader at a fresh stand-in serving one publication."""

    def setUp(self):
        self.standin = StandIn().__enter__()
        self.addCleanup(self.standin.__exit__, None, None, None)
        self.addCleanup(setattr, ghost_probe, "OFFICIAL_ADDRESS", ghost_probe.OFFICIAL_ADDRESS)
        ghost_probe.OFFICIAL_ADDRESS = self.standin.base
        ghost_probe._held.clear()
        self.addCleanup(ghost_probe._held.clear)
        self.standin.serve("source.json", publication())

    def nowhere(self):
        """Point the reader at a port nothing listens on."""
        ghost_probe.OFFICIAL_ADDRESS = "http://127.0.0.1:{0}/tools/ghost-probe/".format(
            free_port()
        )

    def ask_recorder(self, answer="report"):
        calls = []

        def ask(text):
            calls.append(text)
            return answer

        return ask, calls


class ReadTests(ReaderTestCase):
    def test_read_returns_the_publication(self):
        publication_read = ghost_probe.read()
        self.assertEqual(publication_read.edition, "1")
        self.assertEqual(publication_read.words, "PLACEHOLDER WORDS")

    def test_words_and_credit_come_from_the_source(self):
        self.assertEqual(ghost_probe.words(), "PLACEHOLDER WORDS")
        self.assertEqual(
            ghost_probe.credit().splitlines(),
            [
                ghost_probe.CREATOR_LINE,
                "Official Ghost Probe: https://azus.ai/tools/ghost-probe/",
                "Edition used: 1",
                "More Westfield tools: https://azus.ai/tools/",
            ],
        )

    def test_integer_edition_reads_the_numbered_address(self):
        self.standin.serve("editions/1/source.json", publication())
        self.assertEqual(ghost_probe.read(1).edition, "1")
        self.assertIn("/tools/ghost-probe/editions/1/source.json", self.standin.requests)

    def test_bad_edition_name_requests_nothing(self):
        with self.assertRaises(ValueError):
            ghost_probe.read("../x")
        self.assertEqual(self.standin.requests, [])


class StopTests(ReaderTestCase):
    def test_not_https_stops_before_any_request(self):
        ghost_probe.OFFICIAL_ADDRESS = "http://azus.ai/tools/ghost-probe/"
        with self.assertRaises(ghost_probe.GhostProbeUnavailable):
            ghost_probe.read()
        self.assertEqual(self.standin.requests, [])

    def test_unreachable_source_stops(self):
        self.nowhere()
        with self.assertRaises(ghost_probe.GhostProbeUnavailable) as stopped:
            ghost_probe.read()
        self.assertIn("Nothing was run", str(stopped.exception))

    def test_redirect_to_another_place_stops(self):
        self.standin.serve(
            "source.json",
            b"",
            status=302,
            headers={"Location": "http://localhost:{0}/x".format(self.standin.port)},
        )
        with self.assertRaises(ghost_probe.GhostProbeUnavailable):
            ghost_probe.read()

    def test_redirect_on_the_same_host_is_followed(self):
        self.standin.serve(
            "source.json",
            b"",
            status=301,
            headers={"Location": self.standin.base + "current.json"},
        )
        self.standin.serve("current.json", publication())
        self.assertEqual(ghost_probe.read().edition, "1")

    def test_answer_over_two_megabytes_stops(self):
        self.standin.serve("source.json", b" " * (ghost_probe.MAX_BYTES + 1))
        with self.assertRaises(ghost_probe.GhostProbeUnavailable):
            ghost_probe.read()

    def test_html_answer_stops(self):
        self.standin.serve("source.json", b"<!DOCTYPE html><html><body>app</body></html>")
        with self.assertRaises(ghost_probe.GhostProbeUnavailable):
            ghost_probe.read()

    def test_blank_subject_refused(self):
        ask, calls = self.ask_recorder()
        with self.assertRaises(ValueError):
            ghost_probe.run(subject="", boundary="b", ask=ask)
        with self.assertRaises(ValueError):
            ghost_probe.run(subject="   ", boundary="b", ask=ask)
        self.assertEqual(calls, [])

    def test_blank_boundary_refused(self):
        ask, calls = self.ask_recorder()
        with self.assertRaises(ValueError):
            ghost_probe.run(subject="s", boundary=" ", ask=ask)
        self.assertEqual(calls, [])

    def test_prompt_labels(self):
        text = ghost_probe.prompt("care", "moral claims")
        self.assertIn("SUBJECT UNDER TEST: care", text)
        self.assertIn("BOUNDARY: moral claims", text)
        self.assertTrue(text.startswith("PLACEHOLDER WORDS"))

    def test_run_ends_with_credit(self):
        report = ghost_probe.run("care", "moral claims", ask=lambda t: "report")
        self.assertEqual(
            report.rstrip().splitlines()[-4:],
            [
                ghost_probe.CREATOR_LINE,
                "Official Ghost Probe: https://azus.ai/tools/ghost-probe/",
                "Edition used: 1",
                "More Westfield tools: https://azus.ai/tools/",
            ],
        )


class PublicationTests(ReaderTestCase):
    def assert_not_the_publication(self, edition=None):
        with self.assertRaises(ghost_probe.GhostProbeUnavailable):
            ghost_probe.read(edition)

    def test_modes_key_ignored(self):
        self.standin.serve("source.json", publication(modes=["AUDIT", "VISION"]))
        self.assertEqual(ghost_probe.read().words, "PLACEHOLDER WORDS")
        self.assertFalse(hasattr(ghost_probe.read(), "modes"))

    def test_other_tool_is_not_the_publication(self):
        self.standin.serve("source.json", publication(tool="Something Else"))
        self.assert_not_the_publication()

    def test_missing_terms_is_not_the_publication(self):
        self.standin.serve("source.json", publication(terms=None))
        self.assert_not_the_publication()

    def test_terms_as_a_list_are_joined(self):
        self.standin.serve("source.json", publication(terms=["1. a", "2. b"]))
        self.assertEqual(ghost_probe.read().terms, "1. a\n2. b")

    def test_edition_file_for_another_edition_is_not_the_publication(self):
        self.standin.serve("editions/2/source.json", publication(edition=1))
        self.assert_not_the_publication(2)

    def test_missing_edition_served_as_html_stops(self):
        self.standin.serve("editions/9/source.json", b"<!DOCTYPE html><html></html>")
        self.assert_not_the_publication(9)


class CreditTests(ReaderTestCase):
    def report_for(self, answer):
        return ghost_probe.run(subject="d", boundary="b", ask=lambda t: answer)

    def assert_ends_with_credit(self, report):
        credit = ghost_probe.credit().splitlines()
        self.assertEqual(report.rstrip().splitlines()[-4:], credit)

    def test_report_without_credit_gets_four_lines(self):
        report = self.report_for("report")
        self.assert_ends_with_credit(report)
        for line in ghost_probe.credit().splitlines():
            self.assertEqual(report.splitlines().count(line), 1)

    def test_report_with_full_credit_is_unchanged(self):
        answer = "report\n\n" + ghost_probe.credit()
        self.assertEqual(self.report_for(answer), answer)

    def test_report_missing_only_the_edition_line_gets_four_lines(self):
        lines = [l for l in ghost_probe.credit().splitlines() if not l.startswith("Edition used")]
        report = self.report_for("report\n\n" + "\n".join(lines))
        self.assert_ends_with_credit(report)

    def test_report_with_wrong_edition_gets_four_lines(self):
        wrong = ghost_probe.credit().replace("Edition used: 1", "Edition used: 2")
        report = self.report_for("report\n\n" + wrong)
        self.assert_ends_with_credit(report)

    def test_report_with_formatted_credit_gets_four_lines(self):
        formatted = ghost_probe.credit().replace("Edition used: 1", "**Edition used:** 1")
        report = self.report_for("report\n\n" + formatted)
        self.assert_ends_with_credit(report)

    def test_credit_far_above_the_end_gets_four_lines(self):
        answer = "report\n\n" + ghost_probe.credit() + "\n\n" + "x" * 2500
        self.assert_ends_with_credit(self.report_for(answer))


class EditionLockTests(ReaderTestCase):
    def setUp(self):
        super().setUp()
        self.current = publication(
            edition=2,
            words="WORDS 2",
            connections=[{"label": "Azus", "address": "https://azus.ai"}],
        )
        self.standin.serve("source.json", self.current)
        self.standin.serve(
            "editions/1/source.json",
            publication(
                edition=1,
                words="WORDS 1",
                connections=[{"label": "Azus", "address": "https://old.example"}],
            ),
        )

    def test_locked_edition_keeps_its_words(self):
        locked = ghost_probe.read(1)
        self.assertEqual(locked.words, "WORDS 1")
        self.assertEqual(locked.edition, "1")

    def test_locked_edition_takes_the_current_title_block(self):
        locked = ghost_probe.read(1)
        self.assertEqual(locked.connections, (("Azus", "https://azus.ai"),))
        self.assertTrue(locked.title_read_from.endswith("/tools/ghost-probe/source.json"))

    def test_changed_link_reaches_a_locked_program_within_five_minutes(self):
        clock = [0.0]
        with mock.patch.object(ghost_probe.time, "monotonic", lambda: clock[0]):
            ghost_probe.read(1)
            self.current["connections"] = [{"label": "Azus", "address": "https://new.example"}]
            self.standin.serve("source.json", self.current)
            clock[0] = 301.0
            locked = ghost_probe.read(1)
        self.assertEqual(locked.connections, (("Azus", "https://new.example"),))
        self.assertEqual(locked.words, "WORDS 1")

    def test_locked_report_names_the_locked_edition(self):
        report = ghost_probe.run(
            subject="d", boundary="b", ask=lambda t: "r", edition=1
        )
        self.assertEqual(report.rstrip().splitlines()[-2], "Edition used: 1")

    def test_locked_edition_stops_when_current_file_is_unreachable(self):
        self.standin.serve("source.json", b"", status=500)
        with self.assertRaises(ghost_probe.GhostProbeUnavailable):
            ghost_probe.read(1)

    def test_main_with_edition_shows_both_addresses(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ghost_probe.main(["--edition", "1"]), 0)
        printed = out.getvalue()
        self.assertIn(self.standin.base + "editions/1/source.json", printed)
        self.assertIn(self.standin.base + "source.json", printed)


class HoldTests(ReaderTestCase):
    def test_one_reading_is_held_for_five_minutes(self):
        clock = [0.0]
        with mock.patch.object(ghost_probe.time, "monotonic", lambda: clock[0]):
            ghost_probe.read()
            clock[0] = 299.0
            ghost_probe.read()
            clock[0] = 301.0
            ghost_probe.read()
        self.assertEqual(len(self.standin.requests), 2)

    def test_fresh_reads_again(self):
        ghost_probe.read()
        ghost_probe.read(fresh=True)
        self.assertEqual(len(self.standin.requests), 2)


class BoundaryTests(ReaderTestCase):
    def test_writes_nothing_to_disk(self):
        with mock.patch("builtins.open", side_effect=AssertionError("opened a file")):
            report = ghost_probe.run(
                subject="d", boundary="b", ask=lambda text: "report"
            )
        self.assertTrue(report.startswith("report"))

    def test_contacts_only_the_official_address(self):
        reached = []
        real = socket.create_connection

        def connect(address, *args, **kwargs):
            reached.append(address[:2])
            return real(address, *args, **kwargs)

        with mock.patch("socket.create_connection", connect):
            ghost_probe.run(subject="d", boundary="b", ask=lambda text: "r")
        self.assertTrue(reached)
        self.assertEqual(set(reached), {("127.0.0.1", self.standin.port)})

    def test_request_carries_no_subject(self):
        ghost_probe.run(subject="SECRET-DOC", boundary="b", ask=lambda t: "r")
        sent = " ".join(self.standin.requests) + " ".join(
            " ".join("{0}: {1}".format(k, v) for k, v in h.items())
            for h in self.standin.headers
        )
        self.assertNotIn("SECRET-DOC", sent)


class MainTests(ReaderTestCase):
    def test_main_prints_what_it_read(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ghost_probe.main([]), 0)
        printed = out.getvalue()
        self.assertIn("Edition:           1", printed)
        self.assertIn("Terms of use:", printed)
        self.assertIn("Azus", printed)

    def test_main_reports_unreachable_source(self):
        self.nowhere()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(ghost_probe.main([]), 1)
        self.assertIn(ghost_probe.CREATOR_LINE, err.getvalue())


if __name__ == "__main__":
    unittest.main()
