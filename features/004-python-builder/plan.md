# Plan 004: Python Builder Agent

## Implementation Approach

### Phase 1: Prompt Template (10 min)
1. Create `src/prompts/python_builder_prompt.py`
2. Define system prompt with requirements
3. Create `create_python_prompt()` function
4. Test prompt generation

### Phase 2: Parsing Logic (12 min)
1. Implement `parse_code_blocks()` with regex
2. Handle edge cases (missing markers, malformed blocks)
3. Test with sample responses

### Phase 3: File Writing (8 min)
1. Implement `write_files()` function
2. Handle directory creation
3. Handle nested paths
4. Test with temporary directory

### Phase 4: Claude API Integration (15 min)
1. Create `src/agents/python_builder.py`
2. Implement `build()` function
3. Add Claude API call
4. Add error handling
5. Update state appropriately

### Phase 5: Workflow Integration (5 min)
1. Import builder in workflow.py
2. Replace placeholder with actual function
3. Test end-to-end

### Phase 6: Testing (10 min)
1. Create unit tests
2. Create integration test with mocked API
3. Manual testing with real API

## Key Decisions

1. **Parsing Strategy**: Use regex to extract code blocks with `filename:` marker
2. **File Format**: Claude outputs ```filename: path\n[content]```
3. **Error Handling**: Catch all exceptions, populate state errors
4. **Directory Structure**: Flat structure by default, Claude determines organization
5. **API Model**: Use Sonnet 4.5 (good balance of speed and quality)
6. **Max Tokens**: 4096 (enough for small-medium apps)

## Implementation Order

1. ✅ Create prompt template (foundation)
2. ✅ Implement parsing logic (needed for builder)
3. ✅ Implement file writing (needed for builder)
4. ✅ Implement builder with API (main logic)
5. ✅ Integrate with workflow
6. ✅ Test

## Prompt Engineering

### System Prompt Strategy
- Clear role definition (expert Python dev)
- Specific output format requirements
- List of technical requirements
- Best practices to follow

### Output Format
Using markdown code blocks with filename marker:
```
```filename: path/to/file.py
[content]
```
```

This format is:
- Easy to parse with regex
- Clear to Claude
- Handles nested directories

## Parsing Strategy

### Regex Pattern
```python
pattern = r'```filename:\s*(.+?)\n(.*?)```'
```

Breaks down as:
- ````filename:` - Literal marker
- `\s*` - Optional whitespace
- `(.+?)` - Capture filepath (non-greedy)
- `\n` - Newline
- `(.*?)` - Capture content (non-greedy)
- ````\` - End marker

### Edge Cases
- Multiple consecutive code blocks
- Code blocks without filename marker (ignore)
- Empty code blocks (skip)
- Nested directory paths (create parent dirs)

## Error Handling

### API Errors
```python
try:
    response = client.messages.create(...)
except APIError as e:
    # Rate limit, auth error, etc.
    state["errors"].append(f"API error: {e}")
except Exception as e:
    # Unexpected errors
    state["errors"].append(f"Unexpected: {e}")
```

### Parsing Errors
- No files found → Error
- Malformed response → Error
- Invalid file paths → Error

### File System Errors
- Permission denied → Error
- Disk full → Error
- Invalid path → Error

## Testing Strategy

### Unit Tests
1. `test_parse_code_blocks` - Various formats
2. `test_write_files` - File creation
3. `test_prompt_creation` - Prompt formatting

### Integration Tests (with mocks)
```python
def test_build_success(monkeypatch):
    """Mock successful API call"""
    def mock_create(*args, **kwargs):
        return MockResponse('''
```filename: main.py
print("hello")
```
        ''')

    monkeypatch.setattr("anthropic.Client.messages.create", mock_create)

    state = create_initial_state("test", "test")
    result = build(state)

    assert result["python_output"]["status"] == "success"
```

### Manual Tests
```bash
# Test with real API
python main.py

# Verify files
cat builds/python-test-project/main.py
```

## Potential Issues

1. **Token Limit**: 4096 may not be enough for complex apps
   - Solution: Start with simple apps, increase later if needed

2. **Parsing Failures**: Claude might not follow format exactly
   - Solution: Clear instructions, retry logic

3. **File Path Issues**: Cross-platform path separators
   - Solution: Use pathlib.Path

4. **API Rate Limits**: Too many requests
   - Solution: Add retry with backoff (future)

## Validation Steps

```python
# Quick validation
from src.agents.python_builder import parse_code_blocks

test_content = '''
```filename: main.py
print("hello")
```
'''

files = parse_code_blocks(test_content)
print(files)  # Should have main.py
```

---

**Time Estimate**: 50-60 minutes
**Dependencies**: Spec 001-003
**Risk**: Medium (depends on API reliability)
