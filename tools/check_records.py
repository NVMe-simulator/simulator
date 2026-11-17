"""Check custom naming and include delimiters using Clang's semantic AST."""

import re
import subprocess
import sys
from pathlib import Path

from clang import cindex


RECORDS = {
    cindex.CursorKind.CLASS_DECL,
    cindex.CursorKind.STRUCT_DECL,
    cindex.CursorKind.CLASS_TEMPLATE,
    cindex.CursorKind.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION,
}


def check_fields(record):
    errors = []
    for field in record.get_children():
        if field.kind not in (cindex.CursorKind.FIELD_DECL, cindex.CursorKind.VAR_DECL):
            continue
        if not field.spelling:  # Anonymous unions and unnamed bit-fields.
            continue
        static_constant = field.kind == cindex.CursorKind.VAR_DECL and field.type.is_const_qualified()
        if static_constant:
            pattern, expected = r"k[A-Z][a-zA-Z0-9]*", "kCamelCase"
        elif field.access_specifier == cindex.AccessSpecifier.PRIVATE:
            pattern, expected = r"[A-Z][a-zA-Z0-9]*_", "CamelCase_"
        else:
            pattern, expected = r"[A-Z][a-zA-Z0-9]*", "CamelCase"
        if re.fullmatch(pattern, field.spelling) is None:
            loc = field.location
            errors.append(
                f"{loc.file}:{loc.line}:{loc.column}: {field.spelling}: "
                f"expected {expected} [project-member-naming]"
            )
    return errors


def check_enum(enum):
    errors = []
    nested = enum.semantic_parent.kind in RECORDS
    if nested or enum.is_scoped_enum():
        pattern, expected = r"[A-Z][a-zA-Z0-9]*", "CamelCase without a prefix"
    else:
        initials = "".join(char for char in enum.spelling[1:] if char.isupper())
        if not initials:
            loc = enum.location
            return [f"{loc.file}:{loc.line}:{loc.column}: expected a named EName enum "
                    "[project-enum-naming]"]
        pattern = re.escape(initials) + r"_[A-Z][A-Z0-9]*(_[A-Z0-9]+)*"
        expected = initials + "_UPPER_CASE"
    for value in enum.get_children():
        if value.kind != cindex.CursorKind.ENUM_CONSTANT_DECL:
            continue
        if re.fullmatch(pattern, value.spelling) is None:
            loc = value.location
            errors.append(f"{loc.file}:{loc.line}:{loc.column}: {value.spelling}: "
                          f"expected {expected} [project-enum-naming]")
    return errors


def traits(record, visited=None):
    """Include inherited state and virtual methods, including destructors."""
    visited = set() if visited is None else visited
    key = record.get_usr()
    if key in visited:
        return False, False, False
    visited.add(key)
    has_fields = has_virtual = unresolved = False
    for child in record.get_children():
        if child.kind in (cindex.CursorKind.FIELD_DECL, cindex.CursorKind.VAR_DECL):
            has_fields = True  # Static data also counts as state for this policy.
        elif child.kind in (cindex.CursorKind.CXX_METHOD, cindex.CursorKind.DESTRUCTOR):
            has_virtual |= child.is_virtual_method()
        elif child.kind == cindex.CursorKind.CXX_BASE_SPECIFIER:
            base = child.get_definition()
            if base is None:
                unresolved = True
            else:
                fields, virtual, unknown = traits(base, visited)
                has_fields |= fields
                has_virtual |= virtual
                unresolved |= unknown
    return has_fields, has_virtual, unresolved


def check_include(cursor):
    included = cursor.get_included_file()
    tokens = [token.spelling for token in cursor.get_tokens()]
    if included is None or len(tokens) < 3 or tokens[1] != "include":
        return []
    delimiter = tokens[2][0]
    if delimiter not in ('"', '<'):  # Macro-based includes have no literal delimiter.
        return []
    source_dir = Path(cursor.location.file.name).resolve().parent
    included_dir = Path(included.name).resolve().parent
    expected = '"' if source_dir == included_dir else '<'
    if delimiter == expected:
        return []
    style = (
        '"header.h" for a header in the same directory'
        if expected == '"'
        else '<path/header.h> for a header outside this directory'
    )
    loc = cursor.location
    return [f"{loc.file}:{loc.line}:{loc.column}: use {style} [project-include-delimiters]"]


def check_records(filename, args, project_files):
    """Return diagnostics; parse errors are failures, never a silent skip."""
    if sys.platform == "darwin" and not cindex.Config.loaded:
        # Use Apple's libclang with Apple's SDK. The bundled LLVM 18 library
        # cannot parse newer libc++ headers shipped with Xcode/Command Line Tools.
        compiler = Path(subprocess.check_output(["xcrun", "--find", "clang"], text=True).strip())
        cindex.Config.set_library_file(str(compiler.parent.parent / "lib" / "libclang.dylib"))
    unit = cindex.Index.create().parse(
        str(filename), args=args,
        options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
    )
    errors = [str(d) for d in unit.diagnostics if d.severity >= cindex.Diagnostic.Error]
    if errors:
        return errors
    project_files = {Path(p).resolve() for p in project_files}

    def visit(cursor):
        for child in cursor.get_children():
            if child.location.file is None:
                continue
            if Path(child.location.file.name).resolve() not in project_files:
                continue
            if child.kind == cindex.CursorKind.INCLUSION_DIRECTIVE:
                errors.extend(check_include(child))
                continue
            if child.kind == cindex.CursorKind.ENUM_DECL:
                errors.extend(check_enum(child))
            if child.kind in RECORDS and child.spelling:
                errors.extend(check_fields(child))
                name = child.spelling
                location = f"{child.location.file}:{child.location.line}:{child.location.column}"
                definition = child.get_definition()
                if definition is None:
                    pattern = r"[TI][A-Z][a-zA-Z0-9]*"
                    expected = "TName or IName (forward declaration)"
                else:
                    fields, virtual, unknown = traits(definition)
                    if unknown and not fields:
                        errors.append(
                            f"{location}: cannot classify {name}: unresolved dependent base; "
                            "T/I naming needs review [project-record-naming]"
                        )
                        continue
                    prefix = "I" if virtual and not fields else "T"
                    pattern = prefix + r"[A-Z][a-zA-Z0-9]*"
                    expected = prefix + "Name"
                if re.fullmatch(pattern, name) is None:
                    errors.append(
                        f"{location}: {name}: expected {expected} [project-record-naming]"
                    )
            visit(child)

    visit(unit.cursor)
    return errors
