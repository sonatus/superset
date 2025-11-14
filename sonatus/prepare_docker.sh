#!/usr/bin/env bash
set -e


echo "Switching to script directory..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/.."
cd "$SCRIPT_DIR"
echo "Current directory: $SCRIPT_DIR"


echo "Checking for uv..."
if ! command -v uv &> /dev/null; then
	echo "uv not found, attempting installation via pip..."
	if command -v pip &> /dev/null; then
		pip install --user uv
		echo "uv installed via pip."
	else
		echo "pip not found. Please install uv manually."
		exit 1
	fi
else
	echo "uv is already installed."
fi


echo "Building DB dialect/driver wheel in tsdb-alchemy..."
TSDB_DIR="$SCRIPT_DIR/tsdb-alchemy"
cd "$TSDB_DIR"
uv build
echo "Wheel build complete."


echo "Locating built wheel artifact..."
WHEEL_FILE=$(ls dist/*.whl | head -n 1)
if [ -z "$WHEEL_FILE" ]; then
	echo "No wheel file found in dist/"
	exit 1
fi
echo "Wheel artifact found: $WHEEL_FILE"




echo "Copying wheel to repo-root docker directory..."
cp "$WHEEL_FILE" "$REPO_ROOT/docker/"
echo "Wheel copied to $REPO_ROOT/docker/"


echo "Syncing sonatus/docker contents to repo-root docker..."
SONATUS_DOCKER="$SCRIPT_DIR/docker"
REPO_DOCKER="$REPO_ROOT/docker"
cp -r "$SONATUS_DOCKER/." "$REPO_DOCKER/"
echo "Docker files sync complete."


# echo "Updating docker/requirements-local.txt to reference local wheels..." # TODO: workaround for slow  downloads
# cp "$REPO_DOCKER/requirements-local-vendored.txt" "$REPO_DOCKER/requirements-local.txt"
