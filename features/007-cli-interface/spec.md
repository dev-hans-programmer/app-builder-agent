# Spec 007: CLI Interface with Rich

## Overview
Implement a polished CLI interface using the Rich library for user input, progress indicators, and formatted output.

## Scope

### In Scope
- User input prompts
- Progress indicators during workflow execution
- Formatted output display
- Error message formatting
- Final results summary
- Report preview

### Out of Scope
- GUI interface
- Web interface
- Command-line arguments (future enhancement)
- Configuration file (future enhancement)

## Requirements

### 1. Enhanced main.py

```python
#!/usr/bin/env python3
"""
Dual-Stack Backend Builder Agent

Generates backend applications in both Python (FastAPI) and Node.js (Express)
from a single prompt, then provides intelligent comparison.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.markdown import Markdown

from src.graph.state import create_initial_state, validate_state
from src.graph.workflow import create_workflow

# Load environment variables
load_dotenv()

# Create console
console = Console()


def check_environment() -> bool:
    """
    Check that required environment variables are set.

    Returns:
        True if environment is ready, False otherwise
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        console.print("\n[bold red]❌ Error: ANTHROPIC_API_KEY not found[/bold red]")
        console.print("\nPlease set your API key in .env file:")
        console.print("  ANTHROPIC_API_KEY=your_key_here\n")
        return False

    return True


def display_banner():
    """Display application banner"""
    banner = """
[bold cyan]╔══════════════════════════════════════════════════════╗
║                                                      ║
║      🤖  Dual-Stack Backend Builder Agent  🤖       ║
║                                                      ║
║   Builds your backend in Python & Node.js           ║
║   Then provides intelligent comparison              ║
║                                                      ║
╚══════════════════════════════════════════════════════╝[/bold cyan]
    """
    console.print(banner)


def get_user_input() -> tuple[str, str]:
    """
    Get user input for project details.

    Returns:
        Tuple of (user_prompt, project_name)
    """
    console.print("\n[bold yellow]Let's build your backend application![/bold yellow]\n")

    # Get user prompt
    user_prompt = console.input(
        "[cyan]What backend app do you want to build?[/cyan]\n> "
    )

    if not user_prompt.strip():
        console.print("[red]Error: Prompt cannot be empty[/red]")
        sys.exit(1)

    # Get project name
    project_name = console.input(
        "\n[cyan]Project name:[/cyan]\n> "
    )

    if not project_name.strip():
        console.print("[red]Error: Project name cannot be empty[/red]")
        sys.exit(1)

    return user_prompt, project_name


def display_phase1_start():
    """Display Phase 1 start message"""
    console.print("\n" + "=" * 60)
    console.print("[bold green]Phase 1: Launching Builder Agents[/bold green]")
    console.print("=" * 60)
    console.print("  [cyan]▶[/cyan] python-agent (FastAPI)")
    console.print("  [cyan]▶[/cyan] nodejs-agent (Express)")
    console.print()


def display_phase2_start():
    """Display Phase 2 start message"""
    console.print("\n" + "=" * 60)
    console.print("[bold green]Phase 2: Comparison Analysis[/bold green]")
    console.print("=" * 60)
    console.print()


def display_results(state: dict):
    """
    Display final results with formatted output.

    Args:
        state: Final workflow state
    """
    console.print("\n" + "=" * 60)
    console.print("[bold green]✓ Workflow Complete![/bold green]")
    console.print("=" * 60 + "\n")

    # Build status table
    table = Table(title="Build Summary", show_header=True, header_style="bold magenta")
    table.add_column("Stack", style="cyan", width=20)
    table.add_column("Status", width=15)
    table.add_column("Build Time", justify="right", width=12)
    table.add_column("Files", justify="right", width=10)

    # Python row
    python_output = state.get("python_output", {})
    python_status = python_output.get("status", "unknown")
    python_status_display = "✅ Success" if python_status == "success" else "❌ Failed"
    python_time = state.get("python_build_time", 0)
    python_files = python_output.get("file_count", 0) if python_status == "success" else "-"

    table.add_row(
        "Python (FastAPI)",
        python_status_display,
        f"{python_time:.2f}s",
        str(python_files)
    )

    # Node.js row
    nodejs_output = state.get("nodejs_output", {})
    nodejs_status = nodejs_output.get("status", "unknown")
    nodejs_status_display = "✅ Success" if nodejs_status == "success" else "❌ Failed"
    nodejs_time = state.get("nodejs_build_time", 0)
    nodejs_files = nodejs_output.get("file_count", 0) if nodejs_status == "success" else "-"

    table.add_row(
        "Node.js (Express)",
        nodejs_status_display,
        f"{nodejs_time:.2f}s",
        str(nodejs_files)
    )

    console.print(table)
    console.print()

    # Generated apps paths
    if python_status == "success" or nodejs_status == "success":
        console.print("[bold]📁 Generated Applications:[/bold]")
        if python_status == "success":
            console.print(f"  • {python_output['output_dir']}")
        if nodejs_status == "success":
            console.print(f"  • {nodejs_output['output_dir']}")
        console.print()

    # Comparison report
    report_files = list(Path("./reports").glob("comparison-*.md"))
    if report_files:
        latest_report = max(report_files, key=lambda p: p.stat().st_mtime)
        console.print(f"[bold]📊 Comparison Report:[/bold] {latest_report}\n")

        # Display report preview
        display_report_preview(latest_report)

    # Display errors if any
    if state.get("errors"):
        console.print("\n[bold red]⚠️  Errors Encountered:[/bold red]")
        for error in state["errors"]:
            console.print(f"  • {error}")
        console.print()


def display_report_preview(report_path: Path):
    """
    Display a preview of the comparison report.

    Args:
        report_path: Path to the markdown report
    """
    try:
        with open(report_path, 'r') as f:
            content = f.read()

        # Show first 1000 characters
        preview = content[:1000]
        if len(content) > 1000:
            preview += "\n\n...(report continues)..."

        console.print(Panel(
            Markdown(preview),
            title="[bold cyan]Report Preview[/bold cyan]",
            border_style="cyan"
        ))
        console.print()

    except Exception as e:
        console.print(f"[yellow]Could not preview report: {e}[/yellow]")


def main():
    """Main application entry point"""

    # Display banner
    display_banner()

    # Check environment
    if not check_environment():
        sys.exit(1)

    # Get user input
    user_prompt, project_name = get_user_input()

    # Create initial state
    state = create_initial_state(user_prompt, project_name)

    # Validate state
    errors = validate_state(state)
    if errors:
        console.print("\n[red]Validation errors:[/red]")
        for error in errors:
            console.print(f"  • {error}")
        sys.exit(1)

    # Create workflow
    workflow = create_workflow()

    # Phase 1: Builders
    display_phase1_start()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "[cyan]Building applications...",
            total=None
        )

        # Run workflow
        try:
            final_state = workflow.invoke(state)
            progress.update(task, completed=True)
        except Exception as e:
            progress.update(task, completed=True)
            console.print(f"\n[red]Error: {e}[/red]")
            sys.exit(1)

    # Phase 2: Comparison
    display_phase2_start()
    console.print("[cyan]Analyzing implementations...[/cyan]\n")

    # Display results
    display_results(final_state)

    # Success message
    console.print("[bold green]✨ All done! Happy coding! ✨[/bold green]\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]⚠️  Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]❌ Unexpected error: {e}[/bold red]")
        sys.exit(1)
```

## Success Criteria

- ✅ Banner displays on startup
- ✅ Environment check validates API key
- ✅ User input prompts are clear and styled
- ✅ Progress indicator shows during workflow
- ✅ Phase transitions are clearly marked
- ✅ Results table is formatted nicely
- ✅ Report preview displays markdown correctly
- ✅ Error messages are clear and styled
- ✅ Keyboard interrupt handled gracefully
- ✅ Overall UX is polished and professional

## Testing

### Manual Test
```bash
# Test successful run
python main.py

# Test with missing API key
unset ANTHROPIC_API_KEY
python main.py
# Should show clear error message

# Test keyboard interrupt
python main.py
# Press Ctrl+C during execution
# Should exit gracefully

# Test empty input
python main.py
# Press Enter without typing
# Should show error
```

### Visual Verification
- [ ] Banner looks good
- [ ] Colors are appropriate
- [ ] Progress spinner animates
- [ ] Tables align properly
- [ ] Markdown preview renders
- [ ] Errors are noticeable

## Dependencies

- **Spec 001**: Project setup (Rich library)
- **Spec 002**: State management
- **Spec 003**: Workflow
- **Spec 004-006**: All agents implemented

---

**Status**: Ready for Implementation
**Estimated Time**: 30-35 minutes
