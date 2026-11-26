# Current Architecture

This document describes the codebase as it exists today.

## Overview

`app-builder-agent` is a CLI-driven LangGraph application that takes a single backend prompt, runs two code generators in parallel, and then produces a comparison report. The current implementation targets two stacks:

- Python with FastAPI
- Node.js with Express

The workflow is optimized for fast prototype generation, not for long-running or deeply planned builds.

## Runtime Flow

1. `main.py` loads environment variables and starts the CLI.
2. The user enters a short description of the backend and a project name.
3. `create_initial_state()` builds a `BuilderState` object.
4. `create_workflow()` compiles the LangGraph graph.
5. `parse_input_node()` validates the prompt and project name.
6. `python_builder.build()` and `nodejs_builder.build()` run in parallel.
7. `comparison.compare()` generates a final comparison report.
8. `generate_report_node()` writes the report to `./reports/`.

## Main Components

### CLI Orchestrator

File: [`main.py`](../main.py)

The CLI handles:

- reading user input
- checking environment variables
- showing progress and results
- displaying the generated report preview

It is a presentation layer and workflow launcher, not the business logic layer.

### Workflow Graph

File: [`src/graph/workflow.py`](../src/graph/workflow.py)

The graph is simple and linear after validation:

- parse input
- fan out to the two builders
- converge in comparison
- save report

This is a one-shot workflow with no retry loop, no deep planning phase, and no durable checkpoints.

### Shared State

File: [`src/graph/state.py`](../src/graph/state.py)

The workflow state includes:

- `user_prompt`
- `project_name`
- `python_output`
- `nodejs_output`
- `comparison_report`
- `timestamp`
- `errors`
- `python_build_time`
- `nodejs_build_time`

The `errors` field is configured as an annotated reducer so parallel branches can append safely.

### Builder Agents

Files:

- [`src/agents/python_builder.py`](../src/agents/python_builder.py)
- [`src/agents/nodejs_builder.py`](../src/agents/nodejs_builder.py)

Each builder:

- creates a prompt from the user request
- calls the OpenAI chat completions API
- expects the model to return fenced code blocks in the format `filename: path`
- parses those code blocks into files
- writes the files under `projects/<project-name>/builds/python` or `projects/<project-name>/builds/nodejs`

These agents are currently single-pass generators. They do not:

- break a large requirement into specs
- create implementation tasks
- iterate on failing tests
- repair code automatically
- maintain a durable plan across long builds

### Comparison Agent

File: [`src/agents/comparison.py`](../src/agents/comparison.py)

The comparison agent:

- inspects both build results
- calls the OpenAI API again for analysis
- renders a markdown comparison report

It is a reporting step, not a verification or quality-gating step.

### Prompts

Files:

- [`src/prompts/python_builder_prompt.py`](../src/prompts/python_builder_prompt.py)
- [`src/prompts/nodejs_builder_prompt.py`](../src/prompts/nodejs_builder_prompt.py)
- [`src/prompts/comparison_prompt.py`](../src/prompts/comparison_prompt.py)

These prompts are optimized for direct code generation from a single prompt. They do not currently encode:

- requirement decomposition
- spec files
- acceptance criteria
- task graphs
- verification checkpoints

## Current Strengths

- Very small and easy to reason about
- Parallel code generation for two stacks
- Simple filesystem output model
- Clear CLI feedback
- Existing comparison report generation

## Current Limitations

### 1. No spec-driven decomposition

The system treats the user prompt as an immediate code-generation request. There is no intermediate layer that turns a PRD into:

- bounded requirements
- architecture decisions
- spec documents
- implementation tasks
- validation criteria

### 2. Not designed for medium or complex projects

The current model assumes a project can be generated in one shot. That works for small APIs, but it breaks down for:

- multi-module backends
- authentication and authorization
- background jobs
- database schemas and migrations
- modular domain logic
- multiple iteration passes

### 3. No long-running execution support

There is no persistent job runner, no checkpointing, and no resumable execution model. If a build takes minutes or hours, the current workflow does not have a durable mechanism to:

- pause and resume
- recover from partial failure
- continue after verification failures
- store progress between phases

### 4. Weak verification loop

The workflow generates code and then compares the results, but it does not:

- run tests
- lint generated code
- type-check
- execute build commands
- repair failures automatically

### 5. Flat artifact model

Generated output is written directly to `builds/` and a report to `reports/`. There is no richer artifact structure for:

- spec documents
- task plans
- checkpoints
- test reports
- repair logs
- architecture decisions

## Practical Summary

Today’s architecture is best described as:

> “single-prompt, dual-stack code generation with a final comparison step.”

It is useful for prototypes and small scaffolds, but it is not yet a spec-driven build system for production-grade applications.
