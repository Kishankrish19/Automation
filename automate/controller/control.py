import sys
# sys.stdout.reconfigure(encoding='utf-8') # Uncomment if needed

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt
import subprocess
import os
import time
import json

console = Console()

# --- Configuration ---
# Get the directory where this script is located
CONTROLLER_DIR = os.path.dirname(os.path.abspath(__file__))
CONTROLLER_FILE = os.path.join(CONTROLLER_DIR, "controller.json")

# ---------------------------
# Utility Functions
# ---------------------------
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def load_json(file_path):
    """Loads JSON data from a file."""
    if not os.path.exists(file_path):
        console.print(f"[bold red]Error:[/bold red] File not found: {file_path}")
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        console.print(f"[bold red]Error:[/bold red] Invalid JSON in file: {file_path}")
        return None
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] Could not read file {file_path}: {e}")
        return None

def pause():
    console.input("\nPress [cyan]Enter[/cyan] to continue...")

# ---------------------------
# Task Runner
# ---------------------------
def run_task(task_name, controller_data):
    """
    Looks up the task, builds the command, and runs the script, showing output.
    """
    clear_screen()
    console.rule(f"[bold cyan]🚀 Running Task: {task_name}[/bold cyan]")

    tasks = controller_data.get("tasks", {})
    task_config = tasks.get(task_name)

    if not task_config:
        console.print(f"[bold red]Error:[/bold red] Task '{task_name}' not found in controller tasks.")
        pause()
        return

    script_relative_path = task_config.get("script")
    script_args = task_config.get("args", [])

    if not script_relative_path:
        console.print(f"[bold red]Error:[/bold red] 'script' path missing for task '{task_name}'.")
        pause()
        return

    # Construct absolute paths
    project_root = os.path.dirname(CONTROLLER_DIR)
    script_abs_path = os.path.abspath(os.path.join(project_root, script_relative_path))
    script_dir = os.path.dirname(script_abs_path)
    script_filename = os.path.basename(script_abs_path)

    if not os.path.exists(script_abs_path):
        console.print(f"[bold red]Error:[/bold red] Script file not found: {script_abs_path}")
        pause()
        return

    # Build command
    command = [
        sys.executable,
        "-u", # Unbuffered mode
        script_filename
    ]
    command.extend(script_args)
    command.extend(["--controller", CONTROLLER_FILE])

    console.print(Panel(f"Running command:\n[yellow]{' '.join(command)}[/yellow]\n\nIn directory:\n[yellow]{script_dir}[/yellow]", title="Execution Details", border_style="blue"))
    console.print("\n--- Script Output ---", style="bold blue")

    try:
        # Run the script and stream output directly to the console
        # Use Popen to potentially allow stopping later if needed, but for CLI, run is simpler for now.
        process = subprocess.Popen(
            command,
            cwd=script_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Combine stdout and stderr
            text=True,
            encoding="utf-8",
            bufsize=1, # Line buffered
            env=os.environ.copy() | {"PYTHONUNBUFFERED": "1"} # Force unbuffered
        )

        # Read and print output line by line
        if process.stdout:
            for line in iter(process.stdout.readline, ''):
                console.print(line, end='') # Print line without extra newline

        process.stdout.close()
        return_code = process.wait() # Wait for the process to finish

        if return_code == 0:
             console.print(f"\n--- [bold green]✅ Task '{task_name}' finished successfully![/bold green] ---")
        else:
             console.print(f"\n--- [bold red]❌ Task '{task_name}' exited with code {return_code}[/bold red] ---")

    except FileNotFoundError:
         console.print(f"\n[bold red]Error:[/bold red] Python executable '{sys.executable}' or script '{script_filename}' not found.")
    except Exception as e:
        console.print(f"\n[bold red]⚠️ Failed to run task '{task_name}': {e}[/bold red]")

    pause()

def choose_and_run_task(controller_data):
    """Presents a menu of tasks and runs the chosen one."""
    tasks = controller_data.get("tasks", {})
    if not tasks:
        console.print("[red]No tasks found in controller.json[/red]")
        pause()
        return

    task_names = sorted(list(tasks.keys()))

    while True:
        clear_screen()
        console.rule("[bold blue]Task Runner[/bold blue]")
        table = Table(title="Available Tasks", show_header=True, header_style="bold magenta")
        table.add_column("Option", style="cyan", width=8)
        table.add_column("Task Name", style="green")

        for i, name in enumerate(task_names, start=1):
            table.add_row(str(i), name)
        table.add_row("0", "[red]Back[/red]")
        console.print(table)

        choice = Prompt.ask("\nChoose a task to run")
        if choice == "0":
            return
        elif choice.isdigit() and 1 <= int(choice) <= len(task_names):
            name = task_names[int(choice) - 1]
            run_task(name, controller_data) # Pass controller_data
        else:
            console.print("[red]⚠️ Invalid choice![/red]")
            time.sleep(1)

# --- (Keep Edit/Sync functions if you still want CLI editing) ---
# --- For simplicity, focusing on the Task Runner first ---

# ---------------------------
# Main CLI Menu
# ---------------------------
def main_menu():
    while True:
        controller_data = load_json(CONTROLLER_FILE)
        if not controller_data:
            pause()
            continue # Loop back after error

        clear_screen()
        console.rule("[bold blue]Automation System CLI[/bold blue]")

        table = Table(title="Main Menu", show_header=False)
        table.add_column("Option", style="cyan", width=8)
        table.add_column("Action", style="green")

        table.add_row("1", "Run Tasks")
        # Add options for Edit TXT/JSON back if needed
        # table.add_row("2", "Edit TXT Files")
        # table.add_row("3", "Edit Simple JSON Data")
        table.add_row("0", "[red]Exit[/red]")

        console.print(table)

        choice = Prompt.ask("\nChoose an option")

        if choice == "0":
            console.print("\n[green]Goodbye! 👋[/green]")
            time.sleep(1)
            sys.exit()
        elif choice == "1":
            choose_and_run_task(controller_data)
        # Add elif for other options if re-enabled
        else:
            console.print("[red]⚠️ Invalid choice![/red]")
            time.sleep(1)


if __name__ == "__main__":
    main_menu() 