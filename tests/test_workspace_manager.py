"""Tests for the Workspace Manager helper.

Run from the repository root:

    python3 -m unittest discover -s tests
"""

import collections
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "WorkspaceManager"))

import workspace_manager as wm  # noqa: E402

Run = collections.namedtuple("Run", "status out err notify")


def write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def read_json(path):
    return json.loads(read(path))


def captions(entries):
    return [entry["caption"] for entry in entries]


class TemporaryPackage(unittest.TestCase):
    """Points every file the helper reads or writes into a temporary directory."""

    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        package = os.path.join(self.root.name, "Packages", "WorkspaceManager")
        self.local_dir = os.path.join(self.root.name, "Local")
        os.makedirs(package)
        os.makedirs(self.local_dir)
        self.workspaces_file = os.path.join(package, "workspaces.json")
        self.commands_file = os.path.join(package, "Workspaces.sublime-commands")
        self.menu_file = os.path.join(package, "Main.sublime-menu")
        self.keymap_file = os.path.join(package, "Default.sublime-keymap")
        for name, value in [
            ("WORKSPACES_FILE", self.workspaces_file),
            ("COMMANDS_FILE", self.commands_file),
            ("MENU_FILE", self.menu_file),
            ("KEYMAP_FILE", self.keymap_file),
            ("LOCAL_DIR", self.local_dir),
        ]:
            patcher = mock.patch.object(wm, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def repo(self, name):
        path = os.path.join(self.root.name, "repos", name)
        os.makedirs(path, exist_ok=True)
        return path

    def write_workspaces(self, data):
        write(self.workspaces_file, json.dumps(data))

    def write_session(self, windows, file_name="Auto Save Session.sublime_session"):
        session = {"windows": [{"tabs": [{"path": tab} for tab in tabs]} for tabs in windows]}
        path = os.path.join(self.local_dir, file_name)
        write(path, json.dumps(session))
        return path

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), mock.patch.object(wm, "notify") as notify:
            status = wm.main(list(argv))
        return Run(status, out.getvalue(), err.getvalue(), notify)

    def palette_captions(self):
        return captions(read_json(self.commands_file))


class LenientJsonTest(unittest.TestCase):
    def load(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            handle.write(text)
        self.addCleanup(os.remove, handle.name)
        return wm.load_json_file(handle.name)

    def test_comments_and_trailing_commas_are_ignored(self):
        text = '{\n\t// line comment\n\t"a": [1, 2, /* block\n comment */ 3,],\n\t"b": {},\n}\n'
        self.assertEqual(self.load(text), {"a": [1, 2, 3], "b": {}})

    def test_comment_markers_and_commas_inside_strings_are_kept(self):
        text = '{"url": "http://example.com/x", "glob": "/* literal */", "quote": "say \\"hi\\" // here", "list": "a, ]"}'
        self.assertEqual(self.load(text), {
            "url": "http://example.com/x",
            "glob": "/* literal */",
            "quote": 'say "hi" // here',
            "list": "a, ]",
        })

    def test_comment_between_trailing_comma_and_closing_bracket(self):
        self.assertEqual(self.load("[1, // last\n]"), [1])
        self.assertEqual(self.load("[1, /* last */ ]"), [1])

    def test_windows_line_endings(self):
        self.assertEqual(self.load('{\r\n"a": 1, // c\r\n}\r\n'), {"a": 1})

    def test_shipped_example_and_embedded_default_parse(self):
        example = os.path.join(REPO_ROOT, "WorkspaceManager", "workspaces.example.json")
        self.assertEqual(wm.load_json_file(example), {"workspaces": {}, "notifications": True})
        self.assertEqual(self.load(wm.EMPTY_WORKSPACES_FILE), {"workspaces": {}, "notifications": True})

    def test_invalid_json_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.load('{"a": }')


class LoadWorkspacesTest(TemporaryPackage):
    def test_missing_file_gives_defaults(self):
        self.assertEqual(wm.load_workspaces(), {"workspaces": {}, "notifications": True})

    def test_list_form_is_normalised_to_object_form(self):
        self.write_workspaces({"workspaces": {
            "Web": ["~/web"],
            "Api": {"repos": ["~/api"], "keys": ["ctrl+1"]},
        }})
        data = wm.load_workspaces()
        self.assertEqual(data["workspaces"]["Web"], {"repos": ["~/web"]})
        self.assertEqual(data["workspaces"]["Api"], {"repos": ["~/api"], "keys": ["ctrl+1"]})

    def test_workspace_without_repos_gets_an_empty_list(self):
        self.write_workspaces({"workspaces": {"Empty": {"keys": "ctrl+1"}}})
        self.assertEqual(wm.load_workspaces()["workspaces"]["Empty"]["repos"], [])

    def test_malformed_files_are_usage_errors(self):
        for text in [
            '{"workspaces": [}',
            "[]",
            '{"workspaces": []}',
            '{"workspaces": {"A": 1}}',
            '{"workspaces": {"A": {"repos": [1]}}}',
            '{"workspaces": {"A": {"repos": "~/a"}}}',
        ]:
            with self.subTest(text=text):
                write(self.workspaces_file, text)
                with self.assertRaises(wm.UsageError):
                    wm.load_workspaces()


class SaveWorkspacesTest(TemporaryPackage):
    def test_workspaces_are_sorted_case_insensitively_and_settings_follow(self):
        wm.save_workspaces({
            "notifications": False,
            "workspaces": {"beta": {"repos": []}, "Alpha": {"repos": []}, "Gamma": {"repos": []}},
        })
        text = read(self.workspaces_file)
        self.assertEqual(list(json.loads(text)["workspaces"]), ["Alpha", "beta", "Gamma"])
        self.assertIs(json.loads(text)["notifications"], False)
        self.assertLess(text.index('"workspaces"'), text.index('"notifications"'))
        self.assertFalse(os.path.exists(self.workspaces_file + ".tmp"))


class NameTest(unittest.TestCase):
    def test_names_are_stripped(self):
        self.assertEqual(wm.validate_name("  Backend "), "Backend")

    def test_empty_and_dollar_names_are_rejected(self):
        for name in ["", "   ", "a$b"]:
            with self.subTest(name=name), self.assertRaises(wm.UsageError):
                wm.validate_name(name)


SAMPLE = {"workspaces": {
    "web": ["~/web"],
    "Backend": {"repos": ["~/api", "~/shared"], "keys": "ctrl+alt+1"},
}}

API = os.path.expanduser("~/api")
SHARED = os.path.expanduser("~/shared")


class GenerateTest(TemporaryPackage):
    def setUp(self):
        super().setUp()
        self.write_workspaces(SAMPLE)
        self.data = wm.load_workspaces()
        wm.generate(self.data)
        self.commands = read_json(self.commands_file)
        self.menu = read_json(self.menu_file)
        self.keymap = read_json(self.keymap_file)

    def test_palette_lists_workspaces_sorted_then_global_entries(self):
        self.assertEqual(captions(self.commands), [
            "Workspace: Switch to Backend",
            "Workspace: Open Backend in New Window",
            "Workspace: Open Backend Here",
            "Workspace Manager: Add Current Repository to Backend",
            "Workspace Manager: Remove Current Repository from Backend",
            "Workspace Manager: Rename Backend…",
            "Workspace Manager: Delete Backend",
            "Workspace: Switch to web",
            "Workspace: Open web in New Window",
            "Workspace: Open web Here",
            "Workspace Manager: Add Current Repository to web",
            "Workspace Manager: Remove Current Repository from web",
            "Workspace Manager: Rename web…",
            "Workspace Manager: Delete web",
            "Workspace Manager: Save Open Tabs as Workspace…",
            "Workspace Manager: New Workspace from Current Repository…",
            "Workspace Manager: Edit Workspaces File",
            "Workspace Manager: Regenerate Commands",
        ])

    def test_switch_replaces_the_window_and_opens_repositories_in_order(self):
        switch = self.commands[0]
        self.assertEqual(switch["command"], "chain")
        self.assertEqual(switch["args"]["commands"], [
            ["new_window"],
            ["close_window"],
            ["open_repository", {"path": API}],
            ["open_repository", {"path": SHARED}],
        ])

    def test_open_in_new_window_and_open_here_variants(self):
        opens = [["open_repository", {"path": API}], ["open_repository", {"path": SHARED}]]
        self.assertEqual(self.commands[1]["args"]["commands"], [["new_window"]] + opens)
        self.assertEqual(self.commands[2]["args"]["commands"], opens)

    def test_management_entries_run_the_helper_through_a_git_alias(self):
        self.assertEqual(wm.HELPER_ARGV, [
            "-c", 'alias.wm=!python3 "${packages}/WorkspaceManager/workspace_manager.py"', "wm",
        ])
        add, remove, rename, delete = self.commands[3:7]
        for entry, tail in [
            (add, ["add", "Backend"]),
            (remove, ["remove", "Backend"]),
            (rename, ["rename", "Backend", "$text"]),
            (delete, ["delete", "Backend"]),
        ]:
            self.assertEqual(entry["command"], "git")
            self.assertEqual(entry["args"], {"argv": wm.HELPER_ARGV + tail})
        save, new, _, regenerate = self.commands[-4:]
        self.assertEqual(save["args"]["argv"][-2:], ["save", "$text"])
        self.assertEqual(new["args"]["argv"][-2:], ["new", "$text"])
        self.assertEqual(regenerate["args"]["argv"][-1:], ["generate"])

    def test_edit_file_entry_opens_workspaces_json_with_a_default(self):
        edit = self.commands[-2]
        self.assertEqual(edit["command"], "open_in_editor")
        self.assertEqual(edit["args"]["path"], "${packages}/WorkspaceManager/workspaces.json")
        self.assertEqual(edit["args"]["default"], wm.EMPTY_WORKSPACES_FILE)

    def test_menu_mirrors_the_palette_under_file_workspaces(self):
        self.assertEqual([menu["id"] for menu in self.menu], ["file"])
        workspaces_menu = self.menu[0]["children"][0]
        self.assertEqual(workspaces_menu["caption"], "Workspaces")
        children = workspaces_menu["children"]
        self.assertEqual(captions(children), [
            "Backend", "web", "-",
            "Save Open Tabs as Workspace…", "New Workspace from Current Repository…", "-",
            "Edit Workspaces File", "Regenerate Commands",
        ])
        backend = children[0]["children"]
        self.assertEqual(captions(backend), [
            "Switch", "Open in New Window", "Open Here", "-",
            "Add Current Repository", "Remove Current Repository", "Rename…", "Delete",
        ])
        self.assertEqual(backend[0]["args"], self.commands[0]["args"])
        self.assertEqual(backend[4]["args"], self.commands[3]["args"])

    def test_menu_wraps_text_prompting_commands_in_the_command_palette(self):
        children = self.menu[0]["children"][0]["children"]
        rename = children[0]["children"][6]
        self.assertEqual(rename["command"], "show_command_palette")
        self.assertEqual(rename["args"], {"command": "git", "args": self.commands[5]["args"]})
        save, new = children[3], children[4]
        self.assertEqual(save["command"], "show_command_palette")
        self.assertEqual(save["args"]["args"]["argv"][-2:], ["save", "$text"])
        self.assertEqual(new["args"]["args"]["argv"][-2:], ["new", "$text"])

    def test_keymap_binds_only_workspaces_with_keys(self):
        self.assertEqual(len(self.keymap), 1)
        self.assertEqual(self.keymap[0]["keys"], ["ctrl+alt+1"])
        self.assertEqual(self.keymap[0]["command"], "chain")
        self.assertEqual(self.keymap[0]["args"], self.commands[0]["args"])

    def test_generated_files_carry_no_workspaces_when_none_are_defined(self):
        wm.generate({"workspaces": {}})
        self.assertEqual(self.palette_captions(), captions(self.commands)[-4:])
        children = read_json(self.menu_file)[0]["children"][0]["children"]
        self.assertEqual(captions(children)[0], "Save Open Tabs as Workspace…")
        self.assertEqual(read_json(self.keymap_file), [])

    def test_generate_reports_the_workspace_count(self):
        self.assertEqual(wm.generate(self.data), "generated commands for 2 workspace(s)")


class SessionTest(TemporaryPackage):
    def test_finds_the_tabs_of_the_window_showing_the_repository(self):
        a, b, c = self.repo("a"), self.repo("b"), self.repo("c")
        self.write_session([[a], [b, c]])
        self.assertEqual(wm.tabs_of_window_containing(c), [b, c])
        self.assertEqual(wm.tabs_of_window_containing(a), [a])
        self.assertIsNone(wm.tabs_of_window_containing(self.repo("d")))

    def test_repositories_are_matched_through_symlinks(self):
        a, b = self.repo("a"), self.repo("b")
        link = os.path.join(self.root.name, "link-to-a")
        os.symlink(a, link)
        self.write_session([[a, b]])
        self.assertEqual(wm.tabs_of_window_containing(link), [a, b])

    def test_without_a_session_file_there_is_no_window(self):
        self.assertIsNone(wm.tabs_of_window_containing(self.repo("a")))

    def test_newest_session_file_wins(self):
        a = self.repo("a")
        old = self.write_session([[a, "/old"]], "Session.sublime_session")
        new = self.write_session([[a, "/new"]], "Auto Save Session.sublime_session")
        os.utime(old, (1, 1))
        os.utime(new, (2, 2))
        self.assertEqual(wm.tabs_of_window_containing(a), [a, "/new"])
        os.utime(old, (3, 3))
        self.assertEqual(wm.tabs_of_window_containing(a), [a, "/old"])

    def test_unreadable_session_files_are_skipped(self):
        a = self.repo("a")
        good = self.write_session([[a]], "Session.sublime_session")
        bad = os.path.join(self.local_dir, "Auto Save Session.sublime_session")
        write(bad, "{not json")
        os.utime(good, (1, 1))
        os.utime(bad, (2, 2))
        self.assertEqual(wm.tabs_of_window_containing(a), [a])

    def test_tabs_without_a_path_are_ignored(self):
        a = self.repo("a")
        session = {"windows": [{"tabs": [{"path": a}, {}, {"path": ""}]}]}
        write(os.path.join(self.local_dir, "Session.sublime_session"), json.dumps(session))
        self.assertEqual(wm.tabs_of_window_containing(a), [a])


class CommandTest(TemporaryPackage):
    def setUp(self):
        super().setUp()
        self.api, self.shared, self.web = self.repo("api"), self.repo("shared"), self.repo("web")
        self.write_workspaces({
            "workspaces": {"Backend": {"repos": [self.api], "keys": ["ctrl+1"]}},
            "notifications": False,
        })

    def workspaces(self):
        return read_json(self.workspaces_file)["workspaces"]

    def test_help_and_unknown_commands(self):
        self.assertEqual(self.run_main().status, 0)
        self.assertIn("usage:", self.run_main("--help").out)
        result = self.run_main("bogus")
        self.assertEqual(result.status, 2)
        self.assertIn("unknown command 'bogus'", result.err)

    def test_list_prints_workspaces_and_repositories(self):
        result = self.run_main("list")
        self.assertEqual(result.status, 0)
        self.assertEqual(result.out, "Backend\n    %s\n" % self.api)
        self.write_workspaces({"workspaces": {}})
        self.assertEqual(self.run_main("list").out, "no workspaces defined\n")

    def test_new_creates_a_workspace_and_generates_the_command_files(self):
        result = self.run_main("new", "Frontend", self.web)
        self.assertEqual(result.status, 0)
        self.assertEqual(self.workspaces()["Frontend"], {"repos": [self.web]})
        self.assertIn("Workspace: Switch to Frontend", self.palette_captions())
        self.assertIn("Workspace: Switch to Backend", self.palette_captions())
        result.notify.assert_called_once_with(mock.ANY, "created workspace 'Frontend' with %s" % self.web)

    def test_new_rejects_existing_names_regardless_of_case(self):
        result = self.run_main("new", "backend", self.web)
        self.assertEqual(result.status, 1)
        self.assertIn("already exists", result.err)
        self.assertEqual(list(self.workspaces()), ["Backend"])
        self.assertFalse(os.path.exists(self.commands_file))

    def test_new_requires_a_name_and_an_existing_directory(self):
        self.assertEqual(self.run_main("new").status, 1)
        self.assertEqual(self.run_main("new", "  ", self.web).status, 1)
        missing = os.path.join(self.root.name, "missing")
        result = self.run_main("new", "X", missing)
        self.assertEqual(result.status, 1)
        self.assertIn("is not a directory", result.err)

    def test_add_appends_a_repository_once(self):
        self.assertEqual(self.run_main("add", "backend", self.shared).status, 0)
        self.assertEqual(self.workspaces()["Backend"]["repos"], [self.api, self.shared])
        again = self.run_main("add", "Backend", self.shared)
        self.assertEqual(again.status, 0)
        self.assertIn("already part of workspace", again.out)
        self.assertTrue(again.notify.called)
        self.assertEqual(self.workspaces()["Backend"]["repos"], [self.api, self.shared])

    def test_add_to_unknown_workspace_lists_the_known_ones(self):
        result = self.run_main("add", "Nope", self.shared)
        self.assertEqual(result.status, 1)
        self.assertIn("no workspace named 'Nope' (known: Backend)", result.err)

    def test_remove_drops_the_repository_and_reports_absent_ones(self):
        self.assertEqual(self.run_main("remove", "Backend", self.api).status, 0)
        self.assertEqual(self.workspaces()["Backend"]["repos"], [])
        result = self.run_main("remove", "Backend", self.api)
        self.assertEqual(result.status, 0)
        self.assertIn("is not part of workspace", result.out)

    def test_remove_matches_the_repository_through_a_symlink(self):
        link = os.path.join(self.root.name, "link-to-api")
        os.symlink(self.api, link)
        self.assertEqual(self.run_main("remove", "Backend", link).status, 0)
        self.assertEqual(self.workspaces()["Backend"]["repos"], [])

    def test_delete_removes_the_workspace_and_its_binding(self):
        result = self.run_main("delete", "backend")
        self.assertEqual(result.status, 0)
        self.assertEqual(self.workspaces(), {})
        self.assertEqual(read_json(self.keymap_file), [])
        self.assertNotIn("Workspace: Switch to Backend", self.palette_captions())

    def test_rename_keeps_repositories_and_keys(self):
        result = self.run_main("rename", "backend", "Services")
        self.assertEqual(result.status, 0)
        self.assertEqual(self.workspaces(), {"Services": {"repos": [self.api], "keys": ["ctrl+1"]}})
        self.assertIn("Workspace: Switch to Services", self.palette_captions())
        self.assertNotIn("Workspace: Switch to Backend", self.palette_captions())

    def test_rename_refuses_to_clobber_another_workspace(self):
        self.run_main("new", "Frontend", self.web)
        result = self.run_main("rename", "Backend", "frontend")
        self.assertEqual(result.status, 1)
        self.assertIn("already exists", result.err)
        self.assertEqual(sorted(self.workspaces()), ["Backend", "Frontend"])

    def test_rename_may_change_only_the_case_of_a_name(self):
        result = self.run_main("rename", "Backend", "BACKEND")
        self.assertEqual(result.status, 0)
        self.assertEqual(self.workspaces(), {"BACKEND": {"repos": [self.api], "keys": ["ctrl+1"]}})
        self.assertIn("Workspace: Switch to BACKEND", self.palette_captions())

    def test_rename_requires_both_names(self):
        self.assertEqual(self.run_main("rename", "Backend").status, 1)
        self.assertEqual(self.run_main("rename", "Nope", "X").status, 1)

    def test_save_records_the_tabs_of_the_window_showing_the_repository(self):
        self.write_session([[self.web], [self.api, self.shared]])
        result = self.run_main("save", "Everything", self.shared)
        self.assertEqual(result.status, 0)
        self.assertEqual(self.workspaces()["Everything"], {"repos": [self.api, self.shared]})
        self.assertNotIn("only the current repository", result.out)
        self.assertIn("Workspace: Switch to Everything", self.palette_captions())

    def test_save_overwrites_an_existing_workspace_keeping_its_name_and_keys(self):
        self.write_session([[self.web, self.shared]])
        self.assertEqual(self.run_main("save", "backend", self.web).status, 0)
        self.assertEqual(self.workspaces(), {"Backend": {"repos": [self.web, self.shared], "keys": ["ctrl+1"]}})

    def test_save_without_a_session_records_only_the_repository_and_says_so(self):
        result = self.run_main("save", "Solo", self.web)
        self.assertEqual(result.status, 0)
        self.assertEqual(self.workspaces()["Solo"], {"repos": [self.web]})
        self.assertIn("only the current repository was recorded", result.out)
        notified = result.notify.call_args[0][1]
        self.assertTrue(notified.startswith("saved workspace 'Solo' with 1 repositories"), notified)
        self.assertNotIn("only the current repository", notified)

    def test_only_commands_that_change_workspaces_notify(self):
        self.assertFalse(self.run_main("list").notify.called)
        self.assertFalse(self.run_main("generate").notify.called)
        self.assertFalse(self.run_main("add", "Nope", self.web).notify.called)
        self.assertTrue(self.run_main("delete", "Backend").notify.called)

    def test_generate_rebuilds_files_without_rewriting_a_hand_edited_workspaces_file(self):
        write(self.workspaces_file, '{\n// hand edited\n"workspaces": {"Hand": ["~/hand"],},\n}\n')
        result = self.run_main("generate")
        self.assertEqual(result.status, 0)
        self.assertEqual(result.out, "generated commands for 1 workspace(s)\n")
        self.assertIn("Workspace: Switch to Hand", self.palette_captions())
        self.assertIn("// hand edited", read(self.workspaces_file))

    def test_a_change_that_changes_nothing_leaves_a_hand_edited_file_alone(self):
        write(self.workspaces_file, '{\n// hand edited\n"workspaces": {"Backend": ["%s"]},\n}\n' % self.api)
        self.assertEqual(self.run_main("add", "Backend", self.api).status, 0)
        self.assertEqual(self.run_main("remove", "Backend", self.shared).status, 0)
        self.assertIn("// hand edited", read(self.workspaces_file))

    def test_usage_errors_leave_files_untouched(self):
        before = read(self.workspaces_file)
        self.assertEqual(self.run_main("delete").status, 1)
        self.assertEqual(self.run_main("add", "Backend", os.path.join(self.root.name, "nope")).status, 1)
        self.assertEqual(read(self.workspaces_file), before)
        self.assertFalse(os.path.exists(self.commands_file))


if __name__ == "__main__":
    unittest.main()
