# Workspace Manager for Sublime Merge

## Personal Note

This plugin is entirely vibe coded but I needed something like Sublime Text's "Project Manager".
This was built for my own needs but I figured it might be useful for others as well...

Everything below is written by AI.

## Summary

Named workspaces for Sublime Merge, in the spirit of Sublime Text's
*Project Manager*: a workspace is a list of repositories, and switching to one
opens all of them as tabs in a window.

Sublime Merge has no plugin API (no Python, no package manager), so this
package works with what Sublime Merge does support: command palette entries,
menus, key bindings and the built-in `chain`, `open_repository`, `new_window`
and `close_window` commands. A small Python helper keeps the workspace list in
`workspaces.json` and regenerates the command files whenever it changes.
Sublime Merge runs the helper through its `git` command, using a one-off git
alias, so no changes to your git configuration are needed.

Tested with Sublime Merge build 2132 on Linux.

## Requirements

- Sublime Merge 2 (repository tabs)
- `python3` on your `PATH` (the helper uses only the standard library)
- `git`

## Install

```bash
./install.sh
```

This copies the package to `Packages/WorkspaceManager` inside the Sublime Merge
data directory (`~/.config/sublime-merge` on Linux,
`~/Library/Application Support/Sublime Merge` on macOS), creates an empty
`workspaces.json` and generates the command files. Sublime Merge picks up the
new package while running; no restart is needed.

| Option | Effect |
| --- | --- |
| `--link` | symlink the package folder instead of copying it (handy while developing) |
| `--uninstall` | remove the package; a copy of `workspaces.json` is kept in `Packages/User` |
| `--data-dir DIR` | use a different Sublime Merge data directory |

Reinstalling never overwrites an existing `workspaces.json`.

## Usage

Open the command palette (`Ctrl+P`) and type `Workspace`. Entries starting with
`Workspace:` open workspaces, entries starting with `Workspace Manager:` change
them. The same commands are in *File ▸ Workspaces* for those who keep the menu
bar visible.

| Command | What it does |
| --- | --- |
| `Workspace: Switch to <name>` | Opens the workspace in a new window and closes the current window |
| `Workspace: Open <name> in New Window` | Opens the workspace in a new window, keeps the current one |
| `Workspace: Open <name> Here` | Adds the workspace's repositories as tabs to the current window |
| `Workspace Manager: Save Open Tabs as Workspace…` | Creates (or overwrites) a workspace from the tabs of the current window |
| `Workspace Manager: New Workspace from Current Repository…` | Creates a workspace containing only the current repository |
| `Workspace Manager: Add Current Repository to <name>` | Appends the current repository to a workspace |
| `Workspace Manager: Remove Current Repository from <name>` | Removes the current repository from a workspace |
| `Workspace Manager: Rename <name>…` | Renames a workspace |
| `Workspace Manager: Delete <name>` | Deletes a workspace |
| `Workspace Manager: Edit Workspaces File` | Opens `workspaces.json` in your editor |
| `Workspace Manager: Regenerate Commands` | Rebuilds the command files after editing `workspaces.json` by hand |

A typical start: open the repositories that belong together as tabs, run
*Save Open Tabs as Workspace…*, type a name, press Enter. Later, from any
window, run *Switch to <name>*.

### Key bindings

Give a workspace a `keys` list in `workspaces.json` and a binding that switches
to it is generated:

```json
"Backend": {
	"repos": ["~/Development/api", "~/Development/shared-lib"],
	"keys": ["ctrl+alt+shift+1"]
}
```

### Desktop notifications

After a change the helper shows a desktop notification (`notify-send` on
Linux, Notification Center on macOS) because Sublime Merge itself shows no
output for successful commands. Set `"notifications": false` in
`workspaces.json` to turn this off.

### Command line

The helper can also be used from a terminal; paths default to the current
directory:

```bash
python3 ~/.config/sublime-merge/Packages/WorkspaceManager/workspace_manager.py list
python3 ~/.config/sublime-merge/Packages/WorkspaceManager/workspace_manager.py add Backend ~/Development/api
```

Run it without arguments for the full list of subcommands.

## The workspaces file

`Packages/WorkspaceManager/workspaces.json`:

```json
{
	"workspaces": {
		"Backend": {
			"repos": ["~/Development/api", "~/Development/shared-lib"],
			"keys": ["ctrl+alt+shift+1"]
		},
		"Website": ["~/Development/website"]
	},
	"notifications": true
}
```

Tabs open in the listed order, `~` is expanded, and a workspace may be a plain
list of paths when it needs no key binding. Comments and trailing commas are
accepted when reading, but the helper drops them when it rewrites the file.
After editing by hand, run *Workspace Manager: Regenerate Commands*.

## Behaviour and limitations

These follow from what Sublime Merge's command set allows:

- **Switching replaces the window.** Sublime Merge has no "close all tabs"
  command and quits when the last tab of the last window is closed, so
  *Switch to* opens a new window, closes the window the command ran in, then
  opens the repositories there. Other windows are left alone.
- **Repositories open elsewhere are focused, not duplicated.** If a workspace
  repository is already open in another window, Sublime Merge switches to that
  tab instead of opening it again. The remaining repositories still open in the
  new window.
- **"Save Open Tabs" reads Sublime Merge's auto-saved session**, since that is
  the only place the open tabs are recorded. Sublime Merge writes it every
  couple of minutes, so tabs opened seconds ago may be missing; the command
  then records only the current repository and says so. Run it again a little
  later, or use *Add Current Repository*.
- **Changing workspaces needs an open repository.** Those commands run through
  Sublime Merge's `git` command, which is only available while a repository is
  open in the current tab. Opening and switching workspaces works from any
  window, including an empty one.
- **Windows is untested.** The helper is invoked as `python3`; on Windows the
  interpreter is usually called `python`, so the alias in
  `workspace_manager.py` would need adjusting.

## Development notes

Start Sublime Merge with `--debug` and `"log_commands": true` in your
preferences to see every command it runs on stdout, including the generated
`chain` commands and the `git` invocations of the helper. An isolated instance
for experiments:

```bash
HOME=/tmp/smtest XDG_CONFIG_HOME=/tmp/smtest/.config sublime_merge --multiinstance --debug /path/to/repo
```

The helper's tests use only the standard library; run them from the
repository root:

```bash
python3 -m unittest discover -s tests
```

## License

BSD 3-Clause, see [LICENSE](LICENSE).
