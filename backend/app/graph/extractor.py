"""Deterministic graph extraction (tiers 1-3).

Tier 1 (parser): files, directories, imports, exports, declarations, contains.
Tier 2 (resolver): calls, references, inherits, implements, uses_type — only
  when safely resolvable (same-file definitions or explicitly imported names).
Tier 3 (inferred): data-model support only; disabled by default and never
  emitted unless explicitly enabled.

Never executes repository code. Parse failures degrade to a file node with
whatever deterministic edges survived — one bad file never kills the run.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

GRAPH_LANGUAGES = ("python", "javascript", "typescript")

_JS_IMPORT = re.compile(
    r"""(?:import\s+(?:[^'"]*?\s+from\s+)?|export\s+[^'"]*?\s+from\s+|require\s*\()\s*['"]([^'"]+)['"]"""
)
_JS_EXPORT_NAMED = re.compile(
    r"export\s+(?:async\s+)?(?:class|function|const|let|var|interface|type|enum)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
_JS_DECL = re.compile(
    r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?(class|function|interface|type|enum)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
_JS_METHOD = re.compile(
    r"^\s{2,}(?:async\s+|static\s+|get\s+|set\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\("
)
_JS_CALL = re.compile(r"(?<![\w$.])([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_JS_EXTENDS = re.compile(
    r"class\s+([A-Za-z_][A-Za-z0-9_]*)\s+extends\s+([A-Za-z_][A-Za-z0-9_.]*)"
)
_JS_IMPLEMENTS = re.compile(
    r"class\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+extends\s+[^{]+)?\s+implements\s+([A-Za-z_][A-Za-z0-9_,\s]*)"
)
_JS_KEYWORDS = frozenset(
    {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "function",
        "return",
        "class",
        "import",
        "export",
        "new",
        "typeof",
        "instanceof",
        "void",
        "delete",
        "await",
        "async",
        "constructor",
        "super",
        "this",
    }
)

_PY_MAX_BYTES = 524288


@dataclass
class ExtractedSymbol:
    stable_key: str
    symbol_type: str
    name: str
    qualified_name: str
    path: str
    start_line: int
    end_line: int
    signature: str = ""
    parent_key: str | None = None
    language: str | None = None
    visibility: str | None = None
    provenance: str = "parser"
    metadata: dict = field(default_factory=dict)


@dataclass
class ExtractedRelationship:
    source_key: str
    target_key: str
    relationship_type: str
    confidence: float
    provenance: str
    path: str
    start_line: int
    end_line: int
    excerpt: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:
    symbols: list[ExtractedSymbol] = field(default_factory=list)
    relationships: list[ExtractedRelationship] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


def stable_key(path: str, qualified_name: str, symbol_type: str) -> str:
    return f"{path}::{qualified_name}::{symbol_type}"


def file_key(path: str) -> str:
    return stable_key(path, "(file)", "file")


# --------------------------------------------------------------------------
# Python
# --------------------------------------------------------------------------


def _resolve_py_import(importer: str, raw: str, known_files: set[str]) -> str | None:
    if raw.startswith("."):
        base = (Path(importer).parent / raw).as_posix()
        candidates = [base, base + ".py", f"{base}/__init__.py"]
    else:
        dotted = raw.replace(".", "/")
        candidates = [
            dotted,
            dotted + ".py",
            f"src/{dotted}",
            f"src/{dotted}.py",
            f"{dotted}/__init__.py",
        ]
    for c in candidates:
        norm = c.lstrip("./")
        if norm in known_files:
            return norm
    # `from pkg import submodule`: raw is the package, but the real target
    # may be pkg/submodule.py — try each imported name as a submodule path.
    # Callers pass raw already qualified for plain `import` statements.
    return None


def _resolve_py_from(
    importer: str, module: str, name: str, known_files: set[str]
) -> str | None:
    """Resolve `from <module> import <name>` including submodule imports."""
    direct = _resolve_py_import(importer, module, known_files)
    if not module.startswith("."):
        qualified = f"{module}.{name}" if name != "*" else module
        sub = _resolve_py_import(importer, qualified, known_files)
        if sub is not None:
            return sub
    else:
        base = (Path(importer).parent / module).as_posix()
        for c in (f"{base}/{name}.py", f"{base}/{name}/__init__.py"):
            if c.lstrip("./") in known_files:
                return c.lstrip("./")
    return direct


def _extract_python(
    path: str, source: str, known_files: set[str], out: ExtractionResult
) -> None:
    fk = file_key(path)
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        out.diagnostics.append(f"parse_failed:{path}")
        return
    lines = source.splitlines()
    file_sym_extra: dict[str, ExtractedSymbol] = {}

    def excerpt_at(lineno: int) -> str:
        if 1 <= lineno <= len(lines):
            return lines[lineno - 1].strip()[:500]
        return ""

    # --- declarations -----------------------------------------------------
    class DeclVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.class_stack: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            qn = ".".join([*self.class_stack, node.name])
            end = getattr(node, "end_lineno", None) or node.lineno
            key = stable_key(path, qn, "class")
            out.symbols.append(
                ExtractedSymbol(
                    stable_key=key,
                    symbol_type="class",
                    name=node.name,
                    qualified_name=qn,
                    path=path,
                    start_line=node.lineno,
                    end_line=end,
                    signature=excerpt_at(node.lineno),
                    parent_key=fk,
                    language="python",
                    visibility="private" if node.name.startswith("_") else "public",
                )
            )
            out.relationships.append(
                ExtractedRelationship(
                    source_key=fk,
                    target_key=key,
                    relationship_type="contains",
                    confidence=1.0,
                    provenance="parser",
                    path=path,
                    start_line=node.lineno,
                    end_line=node.lineno,
                    excerpt=excerpt_at(node.lineno),
                )
            )
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()

        def _visit_def(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            kind = "method" if self.class_stack else "function"
            prefix = ".".join(self.class_stack)
            qn = f"{prefix}.{node.name}" if prefix else node.name
            end = getattr(node, "end_lineno", None) or node.lineno
            key = stable_key(path, qn, kind)
            out.symbols.append(
                ExtractedSymbol(
                    stable_key=key,
                    symbol_type=kind,
                    name=node.name,
                    qualified_name=qn,
                    path=path,
                    start_line=node.lineno,
                    end_line=end,
                    signature=excerpt_at(node.lineno),
                    parent_key=fk,
                    language="python",
                    visibility="private" if node.name.startswith("_") else "public",
                )
            )
            out.relationships.append(
                ExtractedRelationship(
                    source_key=fk,
                    target_key=key,
                    relationship_type="contains",
                    confidence=1.0,
                    provenance="parser",
                    path=path,
                    start_line=node.lineno,
                    end_line=node.lineno,
                    excerpt=excerpt_at(node.lineno),
                )
            )
            # exports: top-level defs are importable → file exports symbol
            if not self.class_stack:
                out.relationships.append(
                    ExtractedRelationship(
                        source_key=fk,
                        target_key=key,
                        relationship_type="exports",
                        confidence=0.95,
                        provenance="parser",
                        path=path,
                        start_line=node.lineno,
                        end_line=node.lineno,
                        excerpt=excerpt_at(node.lineno),
                    )
                )
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_def(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_def(node)

    DeclVisitor().visit(tree)

    # defined names → keys (for safe call/reference resolution)
    defined: dict[str, str] = {}
    for sym in out.symbols:
        if sym.path == path and sym.symbol_type in ("function", "method", "class"):
            defined.setdefault(sym.name, sym.stable_key)

    # --- imports (tier 1) --------------------------------------------------
    import_aliases: dict[str, str | None] = {}  # local name → resolved file or None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                local = alias.asname or top
                target = _resolve_py_import(path, alias.name, known_files)
                lineno = getattr(node, "lineno", 1)
                if target is not None:
                    import_aliases[local] = target
                    out.relationships.append(
                        ExtractedRelationship(
                            source_key=fk,
                            target_key=file_key(target),
                            relationship_type="imports",
                            confidence=1.0,
                            provenance="parser",
                            path=path,
                            start_line=lineno,
                            end_line=lineno,
                            excerpt=excerpt_at(lineno),
                            metadata={"raw": alias.name},
                        )
                    )
                else:
                    import_aliases[local] = None
                    ext_key = stable_key(f"external:{alias.name}", alias.name, "module")
                    if ext_key not in file_sym_extra:
                        file_sym_extra[ext_key] = ExtractedSymbol(
                            stable_key=ext_key,
                            symbol_type="module",
                            name=alias.name,
                            qualified_name=alias.name,
                            path=f"external:{alias.name}",
                            start_line=1,
                            end_line=1,
                            language="python",
                            provenance="parser",
                            metadata={"external": True},
                        )
                    out.relationships.append(
                        ExtractedRelationship(
                            source_key=fk,
                            target_key=ext_key,
                            relationship_type="imports",
                            confidence=0.9,
                            provenance="parser",
                            path=path,
                            start_line=lineno,
                            end_line=lineno,
                            excerpt=excerpt_at(lineno),
                            metadata={"raw": alias.name, "external": True},
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            if not node.module:
                continue
            lineno = getattr(node, "lineno", 1)
            emitted_targets: set[str] = set()
            for alias in node.names:
                local = alias.asname or alias.name
                target = _resolve_py_from(path, node.module, alias.name, known_files)
                if target is not None:
                    import_aliases[local] = target
                    if target not in emitted_targets:
                        emitted_targets.add(target)
                        out.relationships.append(
                            ExtractedRelationship(
                                source_key=fk,
                                target_key=file_key(target),
                                relationship_type="imports",
                                confidence=1.0,
                                provenance="parser",
                                path=path,
                                start_line=lineno,
                                end_line=lineno,
                                excerpt=excerpt_at(lineno),
                                metadata={"raw": f"{node.module}.{alias.name}"},
                            )
                        )
                else:
                    import_aliases[local] = None
            if not emitted_targets:
                target = _resolve_py_import(path, node.module, known_files)
                if target is not None:
                    out.relationships.append(
                        ExtractedRelationship(
                            source_key=fk,
                            target_key=file_key(target),
                            relationship_type="imports",
                            confidence=1.0,
                            provenance="parser",
                            path=path,
                            start_line=lineno,
                            end_line=lineno,
                            excerpt=excerpt_at(lineno),
                            metadata={"raw": node.module},
                        )
                    )
                else:
                    ext_key = stable_key(
                        f"external:{node.module}", node.module, "module"
                    )
                    if ext_key not in file_sym_extra:
                        file_sym_extra[ext_key] = ExtractedSymbol(
                            stable_key=ext_key,
                            symbol_type="module",
                            name=node.module,
                            qualified_name=node.module,
                            path=f"external:{node.module}",
                            start_line=1,
                            end_line=1,
                            language="python",
                            provenance="parser",
                            metadata={"external": True},
                        )
                    out.relationships.append(
                        ExtractedRelationship(
                            source_key=fk,
                            target_key=ext_key,
                            relationship_type="imports",
                            confidence=0.9,
                            provenance="parser",
                            path=path,
                            start_line=lineno,
                            end_line=lineno,
                            excerpt=excerpt_at(lineno),
                            metadata={"raw": node.module, "external": True},
                        )
                    )
    out.symbols.extend(file_sym_extra.values())

    # --- tier 2: calls / references / inheritance / type usage -------------
    # enclosing function for each call site
    func_ranges: list[tuple[int, int, str]] = [
        (s.start_line, s.end_line, s.stable_key)
        for s in out.symbols
        if s.path == path and s.symbol_type in ("function", "method")
    ]

    def enclosing(lineno: int) -> str:
        best = fk
        best_span = None
        for start, end, key in func_ranges:
            if start <= lineno <= end and (
                best_span is None or (end - start) < best_span
            ):
                best, best_span = key, end - start
        return best

    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", 1)
        if isinstance(node, ast.Call):
            callee = None
            attr_base = None
            if isinstance(node.func, ast.Name):
                callee = node.func.id
            elif isinstance(node.func, ast.Attribute):
                callee = node.func.attr
                if isinstance(node.func.value, ast.Name):
                    attr_base = node.func.value.id
            if not callee:
                continue
            src = enclosing(lineno)
            if callee in defined:
                out.relationships.append(
                    ExtractedRelationship(
                        source_key=src,
                        target_key=defined[callee],
                        relationship_type="calls",
                        confidence=0.9,
                        provenance="resolver",
                        path=path,
                        start_line=lineno,
                        end_line=getattr(node, "end_lineno", None) or lineno,
                        excerpt=excerpt_at(lineno),
                    )
                )
            elif callee in import_aliases and import_aliases[callee] is not None:
                out.relationships.append(
                    ExtractedRelationship(
                        source_key=src,
                        target_key=file_key(import_aliases[callee] or ""),
                        relationship_type="calls",
                        confidence=0.75,
                        provenance="resolver",
                        path=path,
                        start_line=lineno,
                        end_line=getattr(node, "end_lineno", None) or lineno,
                        excerpt=excerpt_at(lineno),
                        metadata={"via_import": callee},
                    )
                )
            elif (
                attr_base is not None
                and attr_base in import_aliases
                and import_aliases[attr_base] is not None
            ):
                # `module.attr()` where module was explicitly imported:
                # evidence-backed file-level call edge (not a fabricated
                # symbol-level edge — the target symbol may live in that file).
                out.relationships.append(
                    ExtractedRelationship(
                        source_key=src,
                        target_key=file_key(import_aliases[attr_base] or ""),
                        relationship_type="calls",
                        confidence=0.75,
                        provenance="resolver",
                        path=path,
                        start_line=lineno,
                        end_line=getattr(node, "end_lineno", None) or lineno,
                        excerpt=excerpt_at(lineno),
                        metadata={"via_import": attr_base, "attr": callee},
                    )
                )
            # else: unresolved — honestly skipped, never fabricated
        elif isinstance(node, ast.ClassDef):
            for base in node.bases:
                basename = None
                if isinstance(base, ast.Name):
                    basename = base.id
                elif isinstance(base, ast.Attribute):
                    basename = base.attr
                if basename and basename in defined:
                    out.relationships.append(
                        ExtractedRelationship(
                            source_key=stable_key(
                                path,
                                ".".join(_class_prefix(path, out, node.name)),
                                "class",
                            ),
                            target_key=defined[basename],
                            relationship_type="inherits",
                            confidence=0.9,
                            provenance="resolver",
                            path=path,
                            start_line=getattr(base, "lineno", node.lineno),
                            end_line=getattr(base, "end_lineno", None) or node.lineno,
                            excerpt=excerpt_at(node.lineno),
                        )
                    )
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in defined:
                src = enclosing(getattr(node, "lineno", 1))
                ref_line: int = getattr(node, "lineno", 1) or 1
                ref_end_obj = getattr(node, "end_lineno", None)
                ref_end: int = int(ref_end_obj) if ref_end_obj else ref_line
                # avoid self-edge spam: skip if src IS the definition line itself
                out.relationships.append(
                    ExtractedRelationship(
                        source_key=src,
                        target_key=defined[node.id],
                        relationship_type="references",
                        confidence=0.7,
                        provenance="resolver",
                        path=path,
                        start_line=ref_line,
                        end_line=ref_end,
                        excerpt=excerpt_at(getattr(node, "lineno", 1)),
                    )
                )


def _class_prefix(path: str, out: ExtractionResult, name: str) -> list[str]:
    for sym in out.symbols:
        if sym.path == path and sym.name == name and sym.symbol_type == "class":
            return sym.qualified_name.split(".")
    return [name]


# --------------------------------------------------------------------------
# JavaScript / TypeScript (regex-based, graceful degradation)
# --------------------------------------------------------------------------


def _resolve_js_import(importer: str, raw: str, known_files: set[str]) -> str | None:
    if raw.startswith("."):
        base = (Path(importer).parent / raw).as_posix()
        # strip extension if present, then try candidates
        base_no_ext = re.sub(r"\.(ts|tsx|js|jsx|mjs|cjs)$", "", base)
        for c in (
            base,
            base_no_ext,
            base_no_ext + ".ts",
            base_no_ext + ".tsx",
            base_no_ext + ".js",
            base_no_ext + ".jsx",
            base_no_ext + "/index.ts",
            base_no_ext + "/index.js",
        ):
            if c in known_files:
                return c
        return None
    # bare specifier → external unless it maps to a known file
    dotted = raw.replace(".", "/")
    for c in (dotted, dotted + ".ts", dotted + ".js", f"src/{dotted}.ts"):
        if c in known_files:
            return c
    return None


def _extract_js(
    path: str, source: str, language: str, known_files: set[str], out: ExtractionResult
) -> None:
    fk = file_key(path)
    lines = source.splitlines()

    def excerpt_at(lineno: int) -> str:
        if 1 <= lineno <= len(lines):
            return lines[lineno - 1].strip()[:500]
        return ""

    declared: dict[str, str] = {}
    # declarations (tier 1)
    for lineno, line in enumerate(lines, start=1):
        m = _JS_DECL.match(line)
        if m:
            kind_raw, name = m.group(1), m.group(2)
            kind = {
                "class": "class",
                "function": "function",
                "interface": "interface",
                "type": "type",
                "enum": "enum",
            }.get(kind_raw, "function")
            key = stable_key(path, name, kind)
            declared.setdefault(name, key)
            out.symbols.append(
                ExtractedSymbol(
                    stable_key=key,
                    symbol_type=kind,
                    name=name,
                    qualified_name=name,
                    path=path,
                    start_line=lineno,
                    end_line=lineno,
                    signature=line.strip()[:300],
                    parent_key=fk,
                    language=language,
                )
            )
            out.relationships.append(
                ExtractedRelationship(
                    source_key=fk,
                    target_key=key,
                    relationship_type="contains",
                    confidence=1.0,
                    provenance="parser",
                    path=path,
                    start_line=lineno,
                    end_line=lineno,
                    excerpt=excerpt_at(lineno),
                )
            )
            if "export" in line:
                out.relationships.append(
                    ExtractedRelationship(
                        source_key=fk,
                        target_key=key,
                        relationship_type="exports",
                        confidence=0.95,
                        provenance="parser",
                        path=path,
                        start_line=lineno,
                        end_line=lineno,
                        excerpt=excerpt_at(lineno),
                    )
                )
    for lineno, line in enumerate(lines, start=1):
        m = _JS_EXPORT_NAMED.search(line)
        if m and m.group(1) not in declared:
            name = m.group(1)
            key = stable_key(path, name, "variable")
            declared.setdefault(name, key)
            out.symbols.append(
                ExtractedSymbol(
                    stable_key=key,
                    symbol_type="variable",
                    name=name,
                    qualified_name=name,
                    path=path,
                    start_line=lineno,
                    end_line=lineno,
                    signature=line.strip()[:300],
                    parent_key=fk,
                    language=language,
                )
            )
            out.relationships.append(
                ExtractedRelationship(
                    source_key=fk,
                    target_key=key,
                    relationship_type="exports",
                    confidence=0.9,
                    provenance="parser",
                    path=path,
                    start_line=lineno,
                    end_line=lineno,
                    excerpt=excerpt_at(lineno),
                )
            )

    # imports / exports-from (tier 1)
    for m in _JS_IMPORT.finditer(source):
        raw = m.group(1)
        lineno = source.count("\n", 0, m.start()) + 1
        target = _resolve_js_import(path, raw, known_files)
        if target is not None:
            out.relationships.append(
                ExtractedRelationship(
                    source_key=fk,
                    target_key=file_key(target),
                    relationship_type="imports",
                    confidence=1.0,
                    provenance="parser",
                    path=path,
                    start_line=lineno,
                    end_line=lineno,
                    excerpt=excerpt_at(lineno),
                    metadata={"raw": raw},
                )
            )
        else:
            ext_key = stable_key(f"external:{raw}", raw, "module")
            if not any(s.stable_key == ext_key for s in out.symbols):
                out.symbols.append(
                    ExtractedSymbol(
                        stable_key=ext_key,
                        symbol_type="module",
                        name=raw,
                        qualified_name=raw,
                        path=f"external:{raw}",
                        start_line=1,
                        end_line=1,
                        language=language,
                        provenance="parser",
                        metadata={"external": True},
                    )
                )
            out.relationships.append(
                ExtractedRelationship(
                    source_key=fk,
                    target_key=ext_key,
                    relationship_type="imports",
                    confidence=0.9,
                    provenance="parser",
                    path=path,
                    start_line=lineno,
                    end_line=lineno,
                    excerpt=excerpt_at(lineno),
                    metadata={"raw": raw, "external": True},
                )
            )

    # tier 2: extends / implements / same-file calls
    for m in _JS_EXTENDS.finditer(source):
        child, parent = m.group(1), m.group(2).split(".")[-1]
        lineno = source.count("\n", 0, m.start()) + 1
        if child in declared and parent in declared:
            out.relationships.append(
                ExtractedRelationship(
                    source_key=declared[child],
                    target_key=declared[parent],
                    relationship_type="inherits",
                    confidence=0.85,
                    provenance="resolver",
                    path=path,
                    start_line=lineno,
                    end_line=lineno,
                    excerpt=excerpt_at(lineno),
                )
            )
    for m in _JS_IMPLEMENTS.finditer(source):
        child, parents = m.group(1), m.group(2)
        lineno = source.count("\n", 0, m.start()) + 1
        for parent in re.split(r"[,\s]+", parents):
            parent = parent.strip().split(".")[-1]
            if child in declared and parent in declared:
                out.relationships.append(
                    ExtractedRelationship(
                        source_key=declared[child],
                        target_key=declared[parent],
                        relationship_type="implements",
                        confidence=0.85,
                        provenance="resolver",
                        path=path,
                        start_line=lineno,
                        end_line=lineno,
                        excerpt=excerpt_at(lineno),
                    )
                )
    for m in _JS_CALL.finditer(source):
        callee = m.group(1)
        if callee in _JS_KEYWORDS or callee not in declared:
            continue
        lineno = source.count("\n", 0, m.start()) + 1
        # skip the declaration line itself
        decl = next((s for s in out.symbols if s.stable_key == declared[callee]), None)
        if decl is not None and decl.start_line == lineno:
            continue
        out.relationships.append(
            ExtractedRelationship(
                source_key=fk,
                target_key=declared[callee],
                relationship_type="calls",
                confidence=0.7,
                provenance="resolver",
                path=path,
                start_line=lineno,
                end_line=lineno,
                excerpt=excerpt_at(lineno),
            )
        )


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def extract_files(files: dict[str, tuple[str, str | None]]) -> ExtractionResult:
    """Extract a graph from {rel_path: (content, language)}.

    Always emits file nodes + directory contains edges (tier 1), then
    delegates to language extractors. Unknown languages keep their file
    node and no fabricated edges.
    """
    out = ExtractionResult()
    known_files = set(files.keys())
    # directory nodes
    dirs: set[str] = set()
    for rel in files:
        parts = Path(rel).parent.parts
        for i in range(1, len(parts) + 1):
            dirs.add(Path(*parts[:i]).as_posix())
    dir_keys: dict[str, str] = {}
    for d in sorted(dirs):
        if d in (".", ""):
            continue
        key = stable_key(d, d, "directory")
        dir_keys[d] = key
        out.symbols.append(
            ExtractedSymbol(
                stable_key=key,
                symbol_type="directory",
                name=Path(d).name or d,
                qualified_name=d,
                path=d,
                start_line=1,
                end_line=1,
            )
        )
    for rel, (content, language) in sorted(files.items()):
        fk = file_key(rel)
        parent = Path(rel).parent.as_posix()
        parent_key = dir_keys.get(parent) if parent not in (".", "") else None
        out.symbols.append(
            ExtractedSymbol(
                stable_key=fk,
                symbol_type="file",
                name=Path(rel).name,
                qualified_name=rel,
                path=rel,
                start_line=1,
                end_line=max(1, content.count("\n") + 1),
                language=language,
                metadata={"generated": False},
            )
        )
        if parent_key:
            out.relationships.append(
                ExtractedRelationship(
                    source_key=parent_key,
                    target_key=fk,
                    relationship_type="contains",
                    confidence=1.0,
                    provenance="parser",
                    path=rel,
                    start_line=1,
                    end_line=1,
                )
            )
        if len(content.encode("utf-8", "ignore")) > _PY_MAX_BYTES:
            out.diagnostics.append(f"too_large:{rel}")
            continue
        try:
            if language == "python":
                _extract_python(rel, content, known_files, out)
            elif language in ("javascript", "typescript"):
                _extract_js(rel, content, language, known_files, out)
            else:
                out.diagnostics.append(f"unsupported_language:{rel}")
        except Exception as exc:  # never fail the whole run on one file
            logger.warning(
                "graph_extract_file_failed path=%s error=%s", rel, type(exc).__name__
            )
            out.diagnostics.append(f"extract_failed:{rel}")
    return out
