#!/usr/bin/env bash
# Installs, updates or removes the Workspace Manager package for Sublime Merge.
set -euo pipefail

usage() {
	cat <<'EOF'
usage: install.sh [--link] [--uninstall] [--data-dir DIR]

  --link          symlink the package folder instead of copying it (for development)
  --uninstall     remove the package, keeping a copy of workspaces.json in Packages/User
  --data-dir DIR  Sublime Merge data directory (default: the platform's standard location)
EOF
}

case "$(uname -s)" in
	Darwin) data_dir="$HOME/Library/Application Support/Sublime Merge" ;;
	*) data_dir="${XDG_CONFIG_HOME:-$HOME/.config}/sublime-merge" ;;
esac
mode=copy
uninstall=0

while [ $# -gt 0 ]; do
	case "$1" in
		--link) mode=link ;;
		--uninstall) uninstall=1 ;;
		--data-dir) data_dir="$2"; shift ;;
		-h|--help) usage; exit 0 ;;
		*) usage; exit 2 ;;
	esac
	shift
done

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/WorkspaceManager"
packages_dir="$data_dir/Packages"
dest="$packages_dir/WorkspaceManager"

if [ "$uninstall" = 1 ]; then
	if [ -f "$dest/workspaces.json" ] && [ ! -L "$dest" ]; then
		backup="$packages_dir/User/WorkspaceManager.workspaces.json.bak"
		mkdir -p "$packages_dir/User"
		cp "$dest/workspaces.json" "$backup"
		echo "kept a copy of your workspaces at $backup"
	fi
	rm -rf "$dest"
	echo "removed $dest"
	exit 0
fi

if [ ! -d "$packages_dir" ]; then
	echo "Sublime Merge data directory not found at $data_dir (start Sublime Merge once, or pass --data-dir)" >&2
	exit 1
fi
if ! command -v python3 >/dev/null; then
	echo "python3 is required: the package runs it through a git alias" >&2
	exit 1
fi

if [ "$mode" = link ]; then
	if [ -e "$dest" ] && [ ! -L "$dest" ]; then
		echo "$dest exists and is not a symlink; remove it first or install without --link" >&2
		exit 1
	fi
	ln -sfn "$source_dir" "$dest"
else
	mkdir -p "$dest"
	cp "$source_dir/workspace_manager.py" "$dest/"
fi

if [ ! -e "$dest/workspaces.json" ]; then
	cp "$source_dir/workspaces.example.json" "$dest/workspaces.json"
fi

python3 "$dest/workspace_manager.py" generate
echo "installed to $dest"
echo "open the command palette in Sublime Merge and type \"Workspace\" to get started"
