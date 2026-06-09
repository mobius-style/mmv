"""OPERATE-FR v0.1 harness package.

Modules
-------
- schemas         : dataclass + dict schemas for tasks, labels, results,
                    classifier output.
- adapters        : model adapter abstraction (dummy + reuse of the
                    parent repo's model_client for OpenAI-compatible and
                    local backends).
- classify_route  : transparent rule-based route classifier.
- score           : component-vector scoring. No composite.
- run_eval        : suite runner.
- report          : Markdown reporter for the component vector.
"""
