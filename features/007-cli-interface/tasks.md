# Tasks 007: CLI Interface with Rich

## Task List

### 1. Update Imports in main.py
**Status**: Completed
**Time**: 3 min

Update `main.py` imports to include:
- dotenv.load_dotenv
- Rich components (Console, Panel, Table, Markdown, Progress)
- Workflow and state functions
- pathlib.Path, sys, os

**Acceptance Criteria**:
- All imports work
- No import errors
- Rich library is installed

---

### 2. Implement check_environment()
**Status**: Completed
**Time**: 5 min

Create function that:
- Gets ANTHROPIC_API_KEY from environment
- Returns True if present, False otherwise
- Displays error message if missing (styled with Rich)

**Acceptance Criteria**:
- Returns boolean
- Error message is clear and styled
- Has docstring

---

### 3. Implement display_banner()
**Status**: Completed
**Time**: 5 min

Create function that:
- Displays ASCII art banner
- Uses Rich styling (bold cyan)
- Includes emoji and title

**Acceptance Criteria**:
- Banner looks professional
- Colors render correctly
- Has docstring

---

### 4. Implement get_user_input()
**Status**: Completed
**Time**: 5 min

Create function that:
- Prompts for user prompt (what to build)
- Prompts for project name
- Validates both are non-empty
- Returns tuple of (user_prompt, project_name)
- Exits with error if invalid

**Acceptance Criteria**:
- Input prompts are styled
- Validation works
- Returns correct tuple
- Has docstring

---

### 5. Implement Phase Display Functions
**Status**: Completed
**Time**: 5 min

Create two functions:
- `display_phase1_start()` - Shows Phase 1 header
- `display_phase2_start()` - Shows Phase 2 header

Each should:
- Display styled separator
- Show phase name
- List what's happening

**Acceptance Criteria**:
- Clear visual separation
- Styled appropriately
- Have docstrings

---

### 6. Implement display_results()
**Status**: Completed
**Time**: 12 min

Create function that:
- Creates Rich Table with build summary
- Adds rows for Python and Node.js with:
  - Status (✅/❌)
  - Build time
  - File count
- Displays generated app paths
- Shows comparison report path
- Lists errors if any

**Acceptance Criteria**:
- Table formats correctly
- Status indicators show properly
- All information displayed
- Has docstring

---

### 7. Implement display_report_preview()
**Status**: Completed
**Time**: 7 min

Create function that:
- Takes report path as parameter
- Reads markdown file
- Shows first 1000 characters
- Renders with Rich Markdown in Panel
- Handles file read errors

**Acceptance Criteria**:
- Markdown renders correctly
- Panel looks good
- Error handling works
- Has docstring

---

### 8. Update main() Function
**Status**: Completed
**Time**: 10 min

Update main() to:
- Call display_banner()
- Call check_environment()
- Call get_user_input()
- Create and validate state
- Create workflow
- Call display_phase1_start()
- Show Progress during workflow.invoke()
- Call display_phase2_start()
- Call display_results()
- Show success message
- Handle exceptions:
  - KeyboardInterrupt
  - General Exception

**Acceptance Criteria**:
- Full flow works
- Progress indicator shows
- Error handling works
- Clean exit codes

---

### 9. Test All Scenarios
**Status**: Completed
**Time**: 10 min

Test cases:

**Successful Run**:
```bash
export ANTHROPIC_API_KEY="your_key"
python main.py
# Input: "Build a REST API for tasks"
# Project: "tasks-api"
# Verify: All displays work
```

**Missing API Key**:
```bash
unset ANTHROPIC_API_KEY
python main.py
# Verify: Clear error message, exits
```

**Empty Input**:
```bash
python main.py
# Press Enter without input
# Verify: Validation error
```

**Keyboard Interrupt**:
```bash
python main.py
# Press Ctrl+C during workflow
# Verify: Graceful exit
```

**Acceptance Criteria**:
- All scenarios handled correctly
- No crashes
- Messages are clear

---

### 10. Visual Polish & Testing
**Status**: Completed
**Time**: 8 min

Visual checks:
- [x] Banner displays correctly
- [x] Colors are consistent and readable
- [x] Tables align properly
- [x] Progress spinner animates
- [x] Markdown preview renders
- [x] Error messages are prominent
- [x] Success messages are encouraging
- [x] Overall flow is smooth

Make adjustments as needed for:
- Column widths
- Color choices
- Spacing
- Wording

**Acceptance Criteria**:
- Professional appearance
- Good UX
- No visual glitches
- Consistent styling

---

## Summary

**Total Tasks**: 10
**Estimated Time**: ~70 minutes
**Dependencies**: Spec 001-006 complete

## Checklist

- [x] 1. Update imports
- [x] 2. Implement check_environment()
- [x] 3. Implement display_banner()
- [x] 4. Implement get_user_input()
- [x] 5. Implement phase display functions
- [x] 6. Implement display_results()
- [x] 7. Implement display_report_preview()
- [x] 8. Update main() function
- [x] 9. Test all scenarios
- [x] 10. Visual polish & testing

---

**Status**: Ready to Start
**Note**: This is the final spec - system will be complete after this!
