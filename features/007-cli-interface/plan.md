# Plan 007: CLI Interface with Rich

## Implementation Approach

### Phase 1: Helper Functions (10 min)
1. `check_environment()` - API key validation
2. `display_banner()` - ASCII art banner
3. `get_user_input()` - Input prompts
4. `display_phase1_start()` - Phase 1 message
5. `display_phase2_start()` - Phase 2 message

### Phase 2: Results Display (12 min)
1. `display_results()` - Results table with Rich
2. `display_report_preview()` - Markdown preview

### Phase 3: Main Function (8 min)
1. Update `main()` with all helper calls
2. Add progress indicator during workflow
3. Add error handling
4. Add keyboard interrupt handling

### Phase 4: Testing & Polish (5 min)
1. Test all display functions
2. Verify colors and formatting
3. Test error scenarios
4. Test keyboard interrupt

## Key Decisions

1. **Rich Library Features**:
   - Console for colored output
   - Panel for boxed content
   - Table for structured data
   - Markdown for report preview
   - Progress for loading indicator

2. **Color Scheme**:
   - Cyan: Prompts and info
   - Green: Success messages
   - Red: Errors
   - Yellow: Warnings
   - Magenta: Table headers

3. **Progress Indicator**:
   - Spinner during workflow execution
   - Indeterminate (no total)
   - Simple and not distracting

4. **Error Handling**:
   - Graceful keyboard interrupt
   - Clear error messages
   - Non-zero exit codes

## Implementation Order

1. ✅ Import Rich components
2. ✅ Implement banner and environment check
3. ✅ Implement input functions
4. ✅ Implement phase display functions
5. ✅ Implement results display
6. ✅ Update main() function
7. ✅ Test and polish

## Rich Library Usage

### Console
```python
from rich.console import Console

console = Console()
console.print("[bold cyan]Hello[/bold cyan]")
console.input("[yellow]Name:[/yellow] ")
```

### Panel
```python
from rich.panel import Panel

console.print(Panel("Content here", title="Title"))
```

### Table
```python
from rich.table import Table

table = Table(title="My Table")
table.add_column("Name", style="cyan")
table.add_column("Value", justify="right")
table.add_row("Python", "3.11")
console.print(table)
```

### Progress
```python
from rich.progress import Progress, SpinnerColumn, TextColumn

with Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
) as progress:
    task = progress.add_task("Loading...", total=None)
    # Do work
    progress.update(task, completed=True)
```

### Markdown
```python
from rich.markdown import Markdown

md = Markdown("# Title\n\nContent")
console.print(md)
```

## Banner Design

Using ASCII art with Rich styling:
```
╔══════════════════════════════════════════════════════╗
║                                                      ║
║      🤖  Dual-Stack Backend Builder Agent  🤖       ║
║                                                      ║
║   Builds your backend in Python & Node.js           ║
║   Then provides intelligent comparison              ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
```

## User Flow

1. Display banner
2. Check environment (API key)
3. Get user input (prompt + project name)
4. Validate input
5. Display Phase 1 start
6. Show progress indicator
7. Run workflow
8. Display Phase 2 start
9. Complete workflow
10. Display results table
11. Show generated app paths
12. Display report preview
13. Show errors if any
14. Success message

## Error Handling

### API Key Missing
```
❌ Error: ANTHROPIC_API_KEY not found

Please set your API key in .env file:
  ANTHROPIC_API_KEY=your_key_here
```

### Empty Input
```
Error: Prompt cannot be empty
```

### Workflow Error
```
❌ Unexpected error: [error message]
```

### Keyboard Interrupt
```
⚠️  Interrupted by user
```

## Testing Scenarios

### Happy Path
```bash
python main.py
# Provide inputs
# Verify all displays work
```

### Missing API Key
```bash
unset ANTHROPIC_API_KEY
python main.py
# Should show clear error
```

### Empty Input
```bash
python main.py
# Press Enter without typing
# Should show validation error
```

### Keyboard Interrupt
```bash
python main.py
# Press Ctrl+C
# Should exit gracefully with message
```

## Visual Quality Checks

- [ ] Banner centered and styled
- [ ] Colors are consistent
- [ ] Tables align properly
- [ ] Progress spinner animates smoothly
- [ ] Markdown renders correctly
- [ ] No layout issues
- [ ] Errors are prominent
- [ ] Success messages are encouraging

## Potential Issues

1. **Terminal Width**: Rich handles this automatically
2. **Color Support**: Rich detects and adapts
3. **Unicode Issues**: Test with emoji support
4. **Windows Compatibility**: Rich is cross-platform

## Validation Steps

```bash
# Quick test
python main.py

# Visual checks:
# - Banner displays correctly
# - Colors work
# - Progress spinner shows
# - Table formats properly
# - Markdown preview renders
# - Exit is clean
```

---

**Time Estimate**: 30-35 minutes
**Dependencies**: Spec 001-006
**Risk**: Low (Rich is well-documented)
