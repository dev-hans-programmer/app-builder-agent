# Tasks 006: Comparison Agent

## Task List

### 1. Create Prompt Template
**Status**: Completed
**Time**: 10 min

Create `src/prompts/comparison_prompt.py` with:
- `COMPARISON_SYSTEM_PROMPT` constant (architect role)
- `create_comparison_prompt()` function that:
  - Takes user_prompt, python_output, nodejs_output
  - Formats build status information
  - Structures report sections
  - Returns complete prompt

**Acceptance Criteria**:
- System prompt defines role and requirements
- Prompt includes all necessary metadata
- Report sections are clearly defined
- Has docstring with parameters

---

### 2. Implement create_error_report()
**Status**: Completed
**Time**: 5 min

In `src/agents/comparison.py`, create function that:
- Takes error message as parameter
- Returns formatted markdown error report
- Explains why comparison couldn't be performed

**Acceptance Criteria**:
- Returns valid markdown
- Clear error message
- Has docstring

---

### 3. Implement create_full_report()
**Status**: Completed
**Time**: 8 min

Create function that:
- Takes Claude's report and state
- Adds build status table
- Adds original request
- Adds timestamp footer
- Returns complete formatted report

**Acceptance Criteria**:
- Build status table is accurate
- Markdown formatting is correct
- All metadata included
- Has docstring

---

### 4. Implement compare() Function
**Status**: Completed
**Time**: 20 min

Create main comparison function that:
- Checks builder statuses
- Handles case where both failed (use create_error_report)
- Gets API key from environment
- Creates Anthropic client
- Creates comparison prompt
- Calls Claude API with:
  - Lower temperature (0.3)
  - Higher max_tokens (3000)
- Extracts report from response
- Uses create_full_report() to add metadata
- Updates state with comparison_report
- Handles errors gracefully

**Acceptance Criteria**:
- Handles all status combinations
- API integration works
- Temperature is 0.3
- State updated correctly
- Print statements for visibility
- Has detailed docstring

---

### 5. Update Workflow Integration
**Status**: Completed
**Time**: 3 min

Update `src/graph/workflow.py`:
- Import comparison.compare
- Replace `comparison_placeholder` with actual function

**Acceptance Criteria**:
- Import works
- All placeholders now replaced with real functions
- No import errors

---

### 6. Write Unit Tests
**Status**: Completed
**Time**: 10 min

Create `tests/test_comparison.py`:

**test_create_error_report**:
- Returns valid markdown
- Includes error message

**test_create_full_report**:
- Adds metadata correctly
- Build status table is accurate
- Handles success/failure states

**test_create_comparison_prompt**:
- Includes user prompt
- Includes builder outputs
- Has all required sections

**Acceptance Criteria**:
- Tests pass
- Edge cases covered

---

### 7. Test All Scenarios
**Status**: Completed
**Time**: 15 min

Run workflow and test:

**Scenario 1: Both succeed**
```bash
python main.py
# Input: "Build a REST API for user management"

cat reports/comparison-*.md
# Verify: Full comparison with all sections
```

**Scenario 2: Python only succeeds**
- Modify to make Node.js fail (e.g., wrong API key for that agent)
- Verify partial comparison report

**Scenario 3: Both fail**
- Simulate both failures
- Verify error report

**Acceptance Criteria**:
- All scenarios produce appropriate reports
- Markdown is valid
- Content is relevant
- No crashes

---

### 8. Verify Report Quality
**Status**: Completed
**Time**: 10 min

Check generated report for:
- [x] All required sections present
- [x] Executive summary clear
- [x] Comparison table formatted correctly
- [x] Recommendation is specific and justified
- [x] Markdown renders correctly
- [x] Build status table accurate
- [x] Timestamp present
- [x] No bias toward either stack

**Acceptance Criteria**:
- Report is professional quality
- All sections present
- Clear recommendation
- Good markdown formatting

---

### 9. Manual Quality Test
**Status**: Completed
**Time**: 5 min

Test with real example:
```bash
python main.py
# Input: "Build a REST API for a blog with posts and comments"

# Read report
cat reports/comparison-*.md

# Check quality:
# - Is the analysis insightful?
# - Is the recommendation justified?
# - Are the comparisons balanced?
# - Is it helpful for decision making?
```

**Acceptance Criteria**:
- Report provides value
- Analysis is accurate
- Recommendation makes sense
- User would find it helpful

---

## Summary

**Total Tasks**: 9
**Estimated Time**: ~85 minutes
**Dependencies**: Spec 001-005 complete

## Checklist

- [x] 1. Create prompt template
- [x] 2. Implement create_error_report()
- [x] 3. Implement create_full_report()
- [x] 4. Implement compare() function
- [x] 5. Update workflow integration
- [x] 6. Write unit tests
- [x] 7. Test all scenarios
- [x] 8. Verify report quality
- [x] 9. Manual quality test

---

**Status**: Ready to Start
