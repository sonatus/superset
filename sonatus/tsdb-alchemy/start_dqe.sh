#!/bin/bash
#set -xe

# --- Configuration ---
# Set the main working directory for the commands
WORKDIR="$HOME/repos/rust_workspace"
# Set a directory to store log files (in current working directory)
LOGDIR="$(pwd)/logs"
# Define common command parts
BASE_CMD="./target/debug/snt_tsdb"
DBC_FILE="../tsdb_stest/vehicles/mazda_2017/can_maps.dbc"
POLICY_FILE="../tsdb_stest/vehicles/any/policies/all_phys.json"
TABLES_DIR="$HOME/tsdb"
CAN_FILE="../tsdb_stest/vehicles/mazda_2017/generators/20240922_1.log"
GATEWAY="127.0.0.1:5001"
GATEWAY_SERVER="127.0.0.1:6001"

# FSQL server addresses
LOCAL_FSQL_SERVER="0.0.0.0:52360"
DOCKER_FSQL_SERVER="172.17.0.1:52360"

# Default to DOCKER_FSQL_SERVER, allow override with -l flag
FSQL_SERVER="$DOCKER_FSQL_SERVER"
while getopts "l" opt; do
    case $opt in
        l)
            FSQL_SERVER="$LOCAL_FSQL_SERVER"
            ;;
    esac
done
shift $((OPTIND -1))

# --- State ---
# Array to store the PIDs of our background processes
PIDS=()

# --- Cleanup Function ---
# This function is called when the script receives a signal
# (e.g., Ctrl+C) or exits.
cleanup() {
    echo ""
    echo "Received stop signal. Terminating processes..."
    
    # Check if PIDS array is empty
    if [ ${#PIDS[@]} -eq 0 ]; then
        echo "No processes to kill."
        exit 0
    fi

    # Loop through all PIDs and send SIGTERM (polite kill)
    for pid in "${PIDS[@]}"; do
        if ps -p "$pid" > /dev/null; then # Check if PID exists
            echo "   - Stopping PID $pid (SIGTERM)..."
            kill "$pid" 2>/dev/null
        fi
    done

    # Give them a moment to shut down
    sleep 2

    # Force kill (SIGKILL) any that are still running
    for pid in "${PIDS[@]}"; do
        if ps -p "$pid" > /dev/null; then
            echo "   - Process $pid did not exit. Forcing (SIGKILL)..."
            kill -9 "$pid" 2>/dev/null
        fi
    done

    echo "Cleanup complete."
}

# --- Trap Signals ---
# This 'trap' command watches for signals and runs the 'cleanup'
# function when they are received.
# SIGINT: Sent when you press Ctrl+C
# SIGTERM: Sent by 'kill' or system shutdown
# EXIT: Runs on any script exit, including normal completion or errors
trap cleanup SIGINT SIGTERM EXIT

# --- Main Script ---

# Navigate to the working directory
cd "$WORKDIR" || { echo "Failed to change directory to $WORKDIR"; exit 1; }



echo "Starting all processes..."
echo "Log files will be stored in: $LOGDIR"
echo "------------------------------------------------"



# Create the log and tables directory if they don't exist
mkdir -p "$LOGDIR"
mkdir -p "$TABLES_DIR"

# Note: Added './' to commands and '2>&1' to redirect
# both stdout and stderr to the log file.

cd "$WORKDIR" || { echo "Failed to change directory to $WORKDIR"; exit 1; }
# 1. Start snt_tsdb (vin0001)
echo "Starting snt_tsdb (vin0001)..."
"$BASE_CMD" --dbc "$DBC_FILE" --policy "$POLICY_FILE" --tables "$TABLES_DIR" \
    --can-file "$CAN_FILE" --cloud-db-key vin0001 --cloud-gateway "$GATEWAY" \
    > "$LOGDIR/tsdb_vin0001.log" 2>&1 &
PIDS+=($!) # Store the PID of the last backgrounded process

# 2. Start snt_tsdb (vin0002)
echo "Starting snt_tsdb (vin0002)..."
"$BASE_CMD" --dbc "$DBC_FILE" --policy "$POLICY_FILE" --tables "$TABLES_DIR" \
    --can-file "$CAN_FILE" --cloud-db-key vin0002 --cloud-gateway "$GATEWAY" \
    > "$LOGDIR/tsdb_vin0002.log" 2>&1 &
PIDS+=($!)

sleep 10 # Time to initialize

# 3. Start snt_tsdb_gw
echo "Starting snt_tsdb_gw..."
./target/debug/snt_tsdb_gw --log-level info --tsdb-port 5001 --client-port 6001 \
    > "$LOGDIR/tsdb_gw.log" 2>&1 &
PIDS+=($!)

sleep 10 # time to initialize

# 4. Start snt_dqe
echo "Starting snt_dqe with SQL server: $FSQL_SERVER..."
./target/debug/snt_dqe --log-level info --tsdb-gateway "$GATEWAY_SERVER" --sql-server "$FSQL_SERVER" \
    > "$LOGDIR/dqe.log" 2>&1 &
PIDS+=($!)

echo "------------------------------------------------"
echo "All processes are running."
echo "PIDs: ${PIDS[*]}"
echo ""
echo "To view logs, run (in a new terminal):"
echo "   tail -f $LOGDIR/tsdb_vin0001.log"
echo "   tail -f $LOGDIR/tsdb_vin0002.log"
echo "   tail -f $LOGDIR/tsdb_gw.log"
echo "   tail -f $LOGDIR/dqe.log"
echo ""
echo "Press Ctrl+C in this terminal to stop all processes."
echo ""

# --- Wait ---
# The 'wait' command pauses the script here. It will wait for any of
# the background PIDs to exit. The 'trap' will catch signals
# and allow the 'cleanup' function to run before the script exits.
wait