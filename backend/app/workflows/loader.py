"""Load every *.yaml workflow definition from a directory.

Called once at process startup (app.main's lifespan hook) against
settings.workflow_definitions_dir, so a broken built-in YAML file fails
the container at boot rather than on the first chat request — see issue
#81's DoD ("Invalid definitions fail loudly at startup with a clear error
naming the file and field").

No directory-scan precedent existed in this codebase before this module
(confirmed during planning); this is deliberately a flat glob over the
one configured directory, not a recursive/plugin-style loader — matching
docs/AGENT_LIBRARY.md's "no premature abstraction" stance until a fork
actually needs nested directories or multiple search paths.
"""

from pathlib import Path

import yaml

from app.workflows.schema import WorkflowDef, parse_workflow_definition


def load_workflow_definitions(directory: str) -> dict[str, WorkflowDef]:
    """Parse and validate every *.yaml file directly under directory.

    Returns a dict keyed by each definition's own `name` field (not its
    filename — the two are conventionally the same, e.g. chat.yaml's name
    is "chat", but the definition's name is the identifier that matters
    for registry lookup).

    Raises WorkflowValidationError, naming the offending file, on the
    first invalid definition encountered — callers should let this
    propagate at startup rather than catching it, per the DoD requirement
    that a broken built-in fails the process loudly.
    """
    definitions: dict[str, WorkflowDef] = {}
    directory_path = Path(directory)
    if not directory_path.is_dir():
        return definitions

    for yaml_file in sorted(directory_path.glob("*.yaml")):
        raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        definition = parse_workflow_definition(raw, source_file=yaml_file.name)
        definitions[definition.name] = definition

    return definitions
