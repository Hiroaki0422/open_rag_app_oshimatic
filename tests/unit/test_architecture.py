import ast
from pathlib import Path


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports


def test_domain_and_application_do_not_import_inbound_or_infrastructure_frameworks() -> None:
    forbidden = {"fastapi", "sqlite3", "opensearch", "uvicorn"}
    for package in (Path("src/rag_app/domain"), Path("src/rag_app/application")):
        for path in package.glob("*.py"):
            assert not imported_roots(path) & forbidden, path


def test_no_later_phase_packages_are_materialized() -> None:
    root = Path("src/rag_app")
    absent = {
        "ingestion",
        "indexing",
        "retrieval",
        "generation",
        "evaluation",
        "datasets",
        "workers",
    }
    assert not {path.name for path in root.iterdir() if path.is_dir()} & absent
