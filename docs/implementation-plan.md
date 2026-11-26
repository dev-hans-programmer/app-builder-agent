# Python-Only Implementation Plan

The Python-only product shape is implemented. Ongoing work should preserve these boundaries:

1. One public project-generation target: Python/FastAPI.
2. One graph generation node: `python_builder`.
3. One generated source root: `builds/python`.
4. One quality and repair path using the Python production policy.
5. No language-selection input or cross-language analysis stage.
6. GitHub delivery always publishes the Python build root.

Future improvements should focus on Python generation quality, task conflict handling, repair
accuracy, artifact storage, execution scalability, and delivery reliability.
