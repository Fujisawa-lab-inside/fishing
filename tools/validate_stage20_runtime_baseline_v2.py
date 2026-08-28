#!/usr/bin/env python3
"""Fail-closed validation for the tracked Stage 20 M0 runtime baseline."""

from __future__ import annotations

import ast
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "config/stage20_runtime_baseline_v2.json"
EXPECTED_SCHEMA = "onga-stage20-runtime-baseline-v2"
ASSET_SCHEMA = "onga-stage20-runtime-assets-v2"
TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".mjs", ".py", ".txt", ".yaml", ".yml"}
JS_IMPORT = re.compile(
    r"(?:\bfrom\s*|\bimport\s*\(\s*|\bimport\s*)['\"](\.[^'\"]+)['\"]",
    re.DOTALL,
)
JS_RUNTIME_STRINGS = (
    re.compile(r"'([^'\n]*)'"),
    re.compile(r'"([^"\n]*)"'),
    re.compile(r"`([^`\n]*)`"),
)
LOCAL_RUNTIME_PREFIXES = (
    "./config/",
    "./data/",
    "./docs/",
    "./public/",
    "config/",
    "data/",
    "docs/",
    "public/",
)


class BaselineError(RuntimeError):
    pass


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise BaselineError(f"{code}: {message}")


def read_json(path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), "E_JSON_PATH", f"regular JSON required: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "E_JSON_OBJECT", f"JSON object required: {path}")
    return value


def repo_path(value: Any, label: str) -> tuple[str, Path]:
    require(isinstance(value, str) and value, "E_PATH_TYPE", f"{label} must be a non-empty string")
    pure = PurePosixPath(value)
    require(not pure.is_absolute(), "E_ABSOLUTE_PATH", f"{label} is absolute: {value}")
    require(".." not in pure.parts and "." not in pure.parts, "E_PATH_TRAVERSAL", f"unsafe {label}: {value}")
    normalized = pure.as_posix().rstrip("/")
    require(normalized and normalized == value.rstrip("/"), "E_PATH_NORMALIZATION", f"non-canonical {label}: {value}")
    resolved = ROOT.joinpath(*pure.parts).resolve()
    require(resolved == ROOT or ROOT in resolved.parents, "E_PATH_ESCAPE", f"{label} escapes repository: {value}")
    return normalized, resolved


def git_paths() -> set[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    )
    return {item.decode("utf-8") for item in completed.stdout.split(b"\0") if item}


def git_path_is_ignored(value: str) -> bool:
    completed = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", value],
        cwd=ROOT,
        check=False,
    )
    return completed.returncode == 0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_js_import(source: Path, specifier: str, extensions: list[str]) -> Path:
    candidate = (source.parent / specifier).resolve()
    candidates = [candidate] if candidate.suffix else [candidate.with_suffix(ext) for ext in extensions]
    for item in candidates:
        if item.is_file():
            require(ROOT in item.parents, "E_IMPORT_ESCAPE", f"JavaScript import escapes repository: {source} -> {specifier}")
            return item
    raise BaselineError(f"E_IMPORT_MISSING: JavaScript import not found: {source.relative_to(ROOT)} -> {specifier}")


def javascript_closure(entrypoints: list[str], extensions: list[str]) -> set[Path]:
    queue = [repo_path(value, "JavaScript entrypoint")[1] for value in entrypoints]
    seen: set[Path] = set()
    while queue:
        source = queue.pop()
        require(source.is_file() and not source.is_symlink(), "E_IMPORT_ENTRYPOINT", f"missing JavaScript source: {source}")
        if source in seen:
            continue
        seen.add(source)
        text = source.read_text(encoding="utf-8")
        for specifier in JS_IMPORT.findall(text):
            imported = resolve_js_import(source, specifier, extensions)
            if imported.suffix in {".js", ".mjs"}:
                queue.append(imported)
            else:
                seen.add(imported)
    return seen


def local_python_module(name: str, roots: list[Path]) -> Path | None:
    relative = Path(*name.split("."))
    for root in roots:
        for candidate in (root / relative.with_suffix(".py"), root / relative / "__init__.py"):
            if candidate.is_file():
                return candidate.resolve()
    return None


def python_closure(entrypoints: list[str], module_roots: list[str]) -> set[Path]:
    roots = [repo_path(value, "Python module root")[1] if value != "." else ROOT for value in module_roots]
    queue = [repo_path(value, "Python entrypoint")[1] for value in entrypoints]
    seen: set[Path] = set()
    while queue:
        source = queue.pop()
        require(source.is_file() and not source.is_symlink(), "E_IMPORT_ENTRYPOINT", f"missing Python source: {source}")
        if source in seen:
            continue
        seen.add(source)
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.append(node.module)
        for name in names:
            imported = local_python_module(name, roots)
            if imported is not None:
                require(ROOT in imported.parents, "E_IMPORT_ESCAPE", f"Python import escapes repository: {name}")
                queue.append(imported)
    return seen


def nested_value(value: Any, dotted_path: str) -> Any:
    current = value
    for part in dotted_path.split("."):
        require(isinstance(current, dict) and part in current, "E_DYNAMIC_BINDING_PATH", dotted_path)
        current = current[part]
    return current


def javascript_runtime_literals(paths: set[Path]) -> dict[str, set[str]]:
    local_paths: set[str] = set()
    api_paths: set[str] = set()
    templates: set[str] = set()
    for source in paths:
        if source.suffix not in {".js", ".mjs"}:
            continue
        text = source.read_text(encoding="utf-8")
        for pattern in JS_RUNTIME_STRINGS:
            for match in pattern.finditer(text):
                value = match.group(1)
                if value.startswith("/api/stage20/"):
                    api_paths.add(value)
                if value.startswith("./${"):
                    templates.add(value)
                    continue
                if not value.startswith(LOCAL_RUNTIME_PREFIXES):
                    continue
                if "${" in value:
                    templates.add(value)
                    continue
                local_paths.add(value[2:] if value.startswith("./") else value)
    return {"local": local_paths, "api": api_paths, "templates": templates}


def forbidden_prefix_hits(text: str, prefixes: list[str]) -> list[str]:
    return sorted({prefix for prefix in prefixes if prefix in text})


def json_string_values(value: Any, pointer: str = ""):
    """Yield JSON string values with RFC 6901-style pointers."""

    if isinstance(value, dict):
        for key, child in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            yield from json_string_values(child, f"{pointer}/{escaped}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from json_string_values(child, f"{pointer}/{index}")
    elif isinstance(value, str):
        yield pointer or "/", value


def validate_dynamic_browser_runtime(
    manifest: dict[str, Any],
    assets: dict[str, Any],
    asset_by_path: dict[str, dict[str, Any]],
    tracked: set[str],
    imports: set[Path],
    release_mode: bool,
) -> dict[str, Any]:
    dynamic = manifest.get("dynamicBrowserRuntime")
    require(isinstance(dynamic, dict), "E_DYNAMIC_CONFIG", "dynamic browser runtime inventory is required")
    errors: list[str] = []
    untracked: list[str] = []
    required_paths: dict[str, str] = {}
    group_ids: set[str] = set()
    groups = dynamic.get("requiredTrackedGroups")
    require(isinstance(groups, list) and groups, "E_DYNAMIC_GROUPS", "required tracked groups are missing")
    identity_policies = {
        "git_blob_at_promoted_commit",
        "asset_registry_sha256",
        "binding_manifest_sha256_and_git_blob_at_promoted_commit",
        "consumer_pinned_sha256_and_git_blob_at_promoted_commit",
    }
    for group in groups:
        require(isinstance(group, dict), "E_DYNAMIC_GROUP", "dynamic group must be an object")
        group_id = group.get("id")
        require(isinstance(group_id, str) and group_id and group_id not in group_ids, "E_DYNAMIC_GROUP_ID", str(group_id))
        group_ids.add(group_id)
        role = group.get("role")
        require(isinstance(role, str) and role, "E_DYNAMIC_ROLE", group_id)
        identity_policy = group.get("identityPolicy")
        require(identity_policy in identity_policies, "E_DYNAMIC_IDENTITY_POLICY", group_id)
        require(isinstance(group.get("rationale"), str) and group["rationale"], "E_DYNAMIC_RATIONALE", group_id)
        paths = group.get("paths")
        require(isinstance(paths, list) and paths, "E_DYNAMIC_PATHS", group_id)
        for raw_path in paths:
            value, path = repo_path(raw_path, f"dynamic path in {group_id}")
            require(value not in required_paths, "E_DYNAMIC_DUPLICATE", value)
            required_paths[value] = group_id
            if not path.is_file() or path.is_symlink():
                errors.append(f"E_DYNAMIC_MISSING: {value}")
                continue
            if identity_policy == "asset_registry_sha256" and value not in asset_by_path:
                errors.append(f"E_DYNAMIC_ASSET_BINDING: {value}")
            if value not in tracked:
                untracked.append(value)
                if release_mode:
                    errors.append(f"E_UNTRACKED_DYNAMIC_REQUIRED: {value}")
    require(
        len(required_paths) == dynamic.get("expectedRequiredTrackedPathCount"),
        "E_DYNAMIC_COUNT",
        f"expected {dynamic.get('expectedRequiredTrackedPathCount')} dynamic paths, found {len(required_paths)}",
    )

    asset_by_id = {asset.get("id"): asset for asset in assets.get("assets", [])}
    optional_ids = dynamic.get("optionalExternalAssetIds")
    require(isinstance(optional_ids, list) and len(optional_ids) == len(set(optional_ids)), "E_DYNAMIC_OPTIONAL_ASSETS", "optional asset ids")
    for asset_id in optional_ids:
        asset = asset_by_id.get(asset_id)
        require(isinstance(asset, dict), "E_DYNAMIC_OPTIONAL_ASSET_UNKNOWN", str(asset_id))
        require(asset.get("trackingPolicy") == "must_not_be_added_to_normal_git", "E_DYNAMIC_OPTIONAL_ASSET_POLICY", str(asset_id))

    collections = assets.get("optionalRuntimeCollections")
    require(isinstance(collections, list), "E_DYNAMIC_COLLECTIONS", "optional runtime collections")
    collection_by_id = {item.get("id"): item for item in collections if isinstance(item, dict)}
    optional_collection_ids = dynamic.get("optionalRuntimeCollectionIds")
    require(
        isinstance(optional_collection_ids, list)
        and len(optional_collection_ids) == len(set(optional_collection_ids)),
        "E_DYNAMIC_COLLECTION_IDS",
        "optional runtime collection ids",
    )
    collection_prefixes: list[str] = []
    for collection_id in optional_collection_ids:
        collection = collection_by_id.get(collection_id)
        require(isinstance(collection, dict), "E_DYNAMIC_COLLECTION_UNKNOWN", str(collection_id))
        prefix, prefix_path = repo_path(collection.get("pathPrefix"), "optional runtime collection prefix")
        normalized_prefix = prefix.rstrip("/") + "/"
        require(
            not prefix_path.exists() or prefix_path.is_dir(),
            "E_DYNAMIC_COLLECTION_PATH",
            normalized_prefix,
        )
        require(collection.get("runtimeRequired") is False, "E_DYNAMIC_COLLECTION_REQUIRED", str(collection_id))
        require(collection.get("networkFetchAllowed") is False, "E_DYNAMIC_COLLECTION_NETWORK", str(collection_id))
        metadata_value, metadata_path = repo_path(collection.get("metadataPath"), "optional runtime collection metadata")
        require(metadata_path.is_file() and metadata_value in tracked, "E_DYNAMIC_COLLECTION_METADATA", metadata_value)
        collection_prefixes.append(normalized_prefix)

    binding_manifest_count = 0
    for binding_spec in dynamic.get("bindingManifests", []):
        require(isinstance(binding_spec, dict), "E_DYNAMIC_BINDING_SPEC", "binding manifest spec")
        binding_path_value, binding_path = repo_path(binding_spec.get("path"), "binding manifest path")
        require(binding_path_value in required_paths, "E_DYNAMIC_BINDING_MANIFEST_REQUIRED", binding_path_value)
        binding_manifest = read_json(binding_path)
        bindings = binding_manifest.get(binding_spec.get("bindingsKey"))
        require(isinstance(bindings, list), "E_DYNAMIC_BINDINGS", binding_path_value)
        binding_by_id = {
            item.get("id"): item for item in bindings if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        require(len(binding_by_id) == len(bindings), "E_DYNAMIC_BINDING_IDS", binding_path_value)
        required_ids = binding_spec.get("requiredBindingIds")
        optional_bindings = binding_spec.get("optionalExternalBindings")
        require(isinstance(required_ids, list) and len(required_ids) == len(set(required_ids)), "E_DYNAMIC_REQUIRED_BINDING_IDS", binding_path_value)
        require(isinstance(optional_bindings, dict), "E_DYNAMIC_OPTIONAL_BINDINGS", binding_path_value)
        consumed_ids = nested_value(binding_manifest, binding_spec.get("consumedIdsPath"))
        expected_ids = set(required_ids) | set(optional_bindings)
        require(isinstance(consumed_ids, list) and set(consumed_ids) == expected_ids, "E_DYNAMIC_CONSUMED_BINDINGS", binding_path_value)
        for binding_id in sorted(expected_ids):
            binding = binding_by_id.get(binding_id)
            require(isinstance(binding, dict), "E_DYNAMIC_BINDING_MISSING", f"{binding_path_value}: {binding_id}")
            value, path = repo_path(binding.get("path"), f"binding {binding_id}")
            if binding_id in optional_bindings:
                asset = asset_by_id.get(optional_bindings[binding_id])
                require(isinstance(asset, dict) and asset.get("path") == value, "E_DYNAMIC_OPTIONAL_BINDING_ASSET", binding_id)
            else:
                require(value in required_paths, "E_DYNAMIC_BINDING_UNDECLARED", f"{binding_id}: {value}")
            if path.exists():
                require(path.is_file() and not path.is_symlink(), "E_DYNAMIC_BINDING_PATH", value)
                require(path.stat().st_size == binding.get("byteLength"), "E_DYNAMIC_BINDING_LENGTH", value)
                require(sha256(path) == binding.get("sha256"), "E_DYNAMIC_BINDING_SHA256", value)
        binding_manifest_count += 1

    literals = javascript_runtime_literals(imports)
    composed_prefixes: list[str] = []
    for declaration in dynamic.get("composedPathDeclarations", []):
        require(isinstance(declaration, dict), "E_DYNAMIC_COMPOSED", "composed path declaration")
        source_value, source_path = repo_path(declaration.get("source"), "composed path source")
        require(source_path in imports, "E_DYNAMIC_COMPOSED_SOURCE", source_value)
        prefix, _ = repo_path(declaration.get("literalPrefix"), "composed literal prefix")
        normalized_prefix = prefix.rstrip("/") + "/"
        require(normalized_prefix in literals["local"], "E_DYNAMIC_COMPOSED_LITERAL", normalized_prefix)
        resolved = declaration.get("resolvedPaths")
        require(isinstance(resolved, list) and resolved, "E_DYNAMIC_COMPOSED_PATHS", normalized_prefix)
        for raw_path in resolved:
            value, _ = repo_path(raw_path, "composed resolved path")
            require(value in required_paths or value in asset_by_path, "E_DYNAMIC_COMPOSED_UNDECLARED", value)
        composed_prefixes.append(normalized_prefix)

    allowed_templates = dynamic.get("allowedTemplateExpressions")
    require(isinstance(allowed_templates, list), "E_DYNAMIC_TEMPLATES", "allowed template expressions")
    if literals["templates"] != set(allowed_templates):
        errors.append(
            "E_DYNAMIC_TEMPLATE_SET: "
            + json.dumps(sorted(literals["templates"]), ensure_ascii=False)
        )

    for value in sorted(literals["local"]):
        classified = value in required_paths or value in asset_by_path
        classified = classified or any(value.startswith(prefix) for prefix in composed_prefixes)
        classified = classified or any(value.startswith(prefix) for prefix in collection_prefixes)
        if not classified:
            errors.append(f"E_UNDECLARED_DYNAMIC_PATH: {value}")

    allowed_api_prefixes = dynamic.get("allowedSameOriginApiPrefixes")
    require(isinstance(allowed_api_prefixes, list) and allowed_api_prefixes, "E_DYNAMIC_API_PREFIXES", "same-origin API prefixes")
    for value in sorted(literals["api"]):
        prefix = value.split("${", 1)[0].rstrip("/")
        if not any(prefix == allowed or prefix.startswith(allowed.rstrip("/") + "/") for allowed in allowed_api_prefixes):
            errors.append(f"E_UNDECLARED_DYNAMIC_API: {value}")
    for allowed in allowed_api_prefixes:
        if not any(
            value == allowed or value.startswith(allowed.rstrip("/") + "/")
            for value in literals["api"]
        ):
            errors.append(f"E_UNUSED_DYNAMIC_API_ALLOWLIST: {allowed}")

    generated_count = 0
    for generated in dynamic.get("runtimeGeneratedUrls", []):
        require(isinstance(generated, dict), "E_DYNAMIC_GENERATED_URL", "generated URL entry")
        source_value, source_path = repo_path(generated.get("source"), "generated URL source")
        require(source_path in imports, "E_DYNAMIC_GENERATED_SOURCE", source_value)
        require(generated.get("classification") == "local_job_output_only", "E_DYNAMIC_GENERATED_CLASS", source_value)
        expression = generated.get("expression")
        require(isinstance(expression, str) and expression in source_path.read_text(encoding="utf-8"), "E_DYNAMIC_GENERATED_EXPRESSION", str(expression))
        generated_count += 1

    return {
        "errors": sorted(set(errors)),
        "untracked": sorted(set(untracked)),
        "requiredPathCount": len(required_paths),
        "bindingManifestCount": binding_manifest_count,
        "localLiteralCount": len(literals["local"]),
        "apiLiteralCount": len(literals["api"]),
        "templateLiteralCount": len(literals["templates"]),
        "optionalExternalAssetCount": len(optional_ids),
        "optionalRuntimeCollectionCount": len(optional_collection_ids),
        "runtimeGeneratedUrlCount": generated_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--workspace-candidate",
        action="store_true",
        help="Validate content and closure while reporting, but not accepting, required untracked paths.",
    )
    mode.add_argument(
        "--release",
        action="store_true",
        help="Require every baseline path and local import to be tracked.",
    )
    args = parser.parse_args()
    release_mode = bool(args.release)
    manifest_path = DEFAULT_MANIFEST
    require(manifest_path == DEFAULT_MANIFEST, "E_MANIFEST_PATH", "only the canonical M0 manifest may be validated")
    manifest = read_json(manifest_path)
    require(manifest.get("schema") == EXPECTED_SCHEMA and manifest.get("version") == 2, "E_SCHEMA", "baseline identity")
    require(
        manifest.get("status") == "M0_1_CANDIDATE_TRACKING_GATE_ENFORCED",
        "E_STATUS",
        "baseline status",
    )

    tracked = git_paths()
    errors: list[str] = []
    untracked_required: list[str] = []
    checked_paths: list[str] = []
    roles: dict[str, str] = {}
    entries = manifest.get("paths")
    require(isinstance(entries, list) and entries, "E_PATHS", "baseline paths must be a non-empty array")
    for entry in entries:
        try:
            require(isinstance(entry, dict), "E_PATH_ENTRY", "baseline path entry must be an object")
            value, path = repo_path(entry.get("path"), "baseline path")
            require(value not in roles, "E_DUPLICATE_PATH", value)
            role = entry.get("role")
            require(isinstance(role, str) and role, "E_ROLE", f"missing role: {value}")
            roles[value] = role
            require(entry.get("trackedExpectation") == "required", "E_TRACKING_POLICY", f"unexpected tracking policy: {value}")
            require(entry.get("sha256Policy") in {"git_blob_at_promoted_commit", "registry_sha256"}, "E_SHA_POLICY", value)
            require(path.is_file() and not path.is_symlink(), "E_MISSING", value)
            checked_paths.append(value)
            if value not in tracked:
                untracked_required.append(value)
                if release_mode:
                    raise BaselineError(f"E_UNTRACKED_REQUIRED: {value}")
        except BaselineError as error:
            errors.append(str(error))

    asset_path_value, asset_path = repo_path(manifest.get("assetRegistryPath"), "asset registry path")
    assets = read_json(asset_path)
    require(assets.get("schema") == ASSET_SCHEMA and assets.get("version") == 2, "E_ASSET_SCHEMA", asset_path_value)
    asset_by_path: dict[str, dict[str, Any]] = {}
    for asset in assets.get("assets", []):
        value, path = repo_path(asset.get("path"), "asset path")
        require(value not in asset_by_path, "E_ASSET_DUPLICATE", value)
        asset_by_path[value] = asset
        if asset.get("trackingPolicy") == "must_not_be_added_to_normal_git" and value in tracked:
            errors.append(f"E_LARGE_ASSET_TRACKED: {value}")
        if (
            asset.get("trackingPolicy") == "must_not_be_added_to_normal_git"
            and not git_path_is_ignored(value)
        ):
            errors.append(f"E_EXTERNAL_ASSET_NOT_IGNORED: {value}")
        if path.exists():
            try:
                require(path.is_file() and not path.is_symlink(), "E_ASSET_PATH", value)
                require(path.stat().st_size == asset.get("byteLength"), "E_ASSET_LENGTH", value)
                require(sha256(path) == asset.get("sha256"), "E_ASSET_SHA256", value)
            except BaselineError as error:
                errors.append(str(error))

    for value, role in roles.items():
        entry = next(item for item in entries if item["path"] == value)
        if entry["sha256Policy"] == "registry_sha256":
            try:
                require(value in asset_by_path, "E_ASSET_BINDING", value)
            except BaselineError as error:
                errors.append(str(error))

    policy = manifest.get("trackingPolicy", {})
    for value in tracked:
        if any(value.startswith(prefix) for prefix in policy.get("forbiddenTrackedPathPrefixes", [])):
            errors.append(f"E_FORBIDDEN_CACHE_TRACKED: {value}")
        if any(value.endswith(suffix) for suffix in policy.get("forbiddenTrackedPathSuffixes", [])):
            errors.append(f"E_FORBIDDEN_CACHE_TRACKED: {value}")

    closure = manifest.get("importClosure", {})
    try:
        imports = javascript_closure(
            closure.get("javascriptEntrypoints", []), closure.get("javascriptExtensions", [])
        ) | python_closure(
            closure.get("pythonEntrypoints", []), closure.get("pythonModuleRoots", [])
        )
        for path in sorted(imports):
            value = path.relative_to(ROOT).as_posix()
            if value not in tracked:
                untracked_required.append(value)
                if release_mode:
                    errors.append(f"E_UNTRACKED_IMPORT: {value}")
    except (BaselineError, SyntaxError, UnicodeDecodeError) as error:
        errors.append(str(error))
        imports = set()

    dynamic_report = {
        "requiredPathCount": 0,
        "bindingManifestCount": 0,
        "localLiteralCount": 0,
        "apiLiteralCount": 0,
        "templateLiteralCount": 0,
        "optionalExternalAssetCount": 0,
        "optionalRuntimeCollectionCount": 0,
        "runtimeGeneratedUrlCount": 0,
    }
    try:
        dynamic_report = validate_dynamic_browser_runtime(
            manifest,
            assets,
            asset_by_path,
            tracked,
            imports,
            release_mode,
        )
        errors.extend(dynamic_report.pop("errors"))
        untracked_required.extend(dynamic_report.pop("untracked"))
    except (BaselineError, json.JSONDecodeError, OSError, UnicodeDecodeError) as error:
        errors.append(str(error))

    absolute_policy = manifest.get("absolutePathPolicy", {})
    forbidden_prefixes = absolute_policy.get("forbiddenPrefixes", [])
    json_exemptions = absolute_policy.get("jsonValueExemptions", [])
    require(
        isinstance(json_exemptions, list),
        "E_ABSOLUTE_EXEMPTIONS",
        "jsonValueExemptions must be an array",
    )
    exemption_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for exemption in json_exemptions:
        require(
            isinstance(exemption, dict),
            "E_ABSOLUTE_EXEMPTION",
            "absolute path exemption must be an object",
        )
        exemption_path, _ = repo_path(
            exemption.get("path"),
            "absolute path exemption",
        )
        pointer = exemption.get("jsonPointer")
        prefix = exemption.get("forbiddenPrefix")
        value_digest = exemption.get("valueSha256")
        require(
            exemption_path in roles,
            "E_ABSOLUTE_EXEMPTION_PATH",
            exemption_path,
        )
        require(
            isinstance(pointer, str) and pointer.startswith("/"),
            "E_ABSOLUTE_EXEMPTION_POINTER",
            exemption_path,
        )
        require(
            prefix in forbidden_prefixes,
            "E_ABSOLUTE_EXEMPTION_PREFIX",
            exemption_path,
        )
        require(
            isinstance(value_digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", value_digest) is not None,
            "E_ABSOLUTE_EXEMPTION_SHA256",
            exemption_path,
        )
        require(
            exemption.get("runtimeConsumed") is False,
            "E_ABSOLUTE_EXEMPTION_RUNTIME",
            exemption_path,
        )
        require(
            isinstance(exemption.get("reason"), str) and exemption["reason"],
            "E_ABSOLUTE_EXEMPTION_REASON",
            exemption_path,
        )
        key = (exemption_path, pointer, prefix)
        require(
            key not in exemption_by_key,
            "E_ABSOLUTE_EXEMPTION_DUPLICATE",
            exemption_path,
        )
        exemption_by_key[key] = exemption

    used_exemptions: set[tuple[str, str, str]] = set()
    for value, role in roles.items():
        if role not in absolute_policy.get("scanRoles", []) or value == "config/stage20_runtime_baseline_v2.json":
            continue
        path = ROOT / value
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8")
            if path.suffix.lower() == ".json":
                document = json.loads(text)
                for pointer, string_value in json_string_values(document):
                    for prefix in forbidden_prefixes:
                        if prefix not in string_value:
                            continue
                        key = (value, pointer, prefix)
                        exemption = exemption_by_key.get(key)
                        observed_digest = hashlib.sha256(
                            string_value.encode("utf-8")
                        ).hexdigest()
                        if (
                            exemption is None
                            or observed_digest != exemption["valueSha256"]
                        ):
                            errors.append(
                                f"E_FORBIDDEN_ABSOLUTE_PATH: {value}: {pointer}: {prefix}"
                            )
                        else:
                            used_exemptions.add(key)
            else:
                for prefix in forbidden_prefixes:
                    if prefix in text:
                        errors.append(f"E_FORBIDDEN_ABSOLUTE_PATH: {value}: {prefix}")

    for value, pointer, prefix in sorted(
        set(exemption_by_key) - used_exemptions
    ):
        errors.append(
            f"E_UNUSED_ABSOLUTE_PATH_EXEMPTION: {value}: {pointer}: {prefix}"
        )

    source_forbidden_prefixes = list(absolute_policy.get("forbiddenPrefixes", []))
    source_forbidden_prefixes.extend(absolute_policy.get("sourceOnlyForbiddenPrefixes", []))
    absolute_scan_paths: list[str] = []
    for path in sorted(imports):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        value = path.relative_to(ROOT).as_posix()
        absolute_scan_paths.append(value)
        for prefix in forbidden_prefix_hits(
            path.read_text(encoding="utf-8"),
            source_forbidden_prefixes,
        ):
            errors.append(f"E_FORBIDDEN_IMPORT_CLOSURE_PATH: {value}: {prefix}")

    authority = manifest.get("authorityBoundary", {})
    if any(authority.get(key) is not False for key in authority):
        errors.append("E_AUTHORITY_BOUNDARY: every M0 authority flag must be false")

    unique_errors = sorted(set(errors))
    unique_untracked = sorted(set(untracked_required))
    if unique_errors:
        status = "FAIL_M0_BASELINE_NOT_PROMOTABLE"
    elif release_mode:
        status = "PASS_TRACKED_REPRODUCIBLE_BASELINE"
    else:
        status = "PASS_WORKSPACE_CANDIDATE_CONTENT_VALID_TRACKING_PENDING"
    report = {
        "schema": "onga-stage20-runtime-baseline-v2-validation",
        "status": status,
        "validationMode": "release" if release_mode else "workspace_candidate",
        "checkedPathCount": len(checked_paths),
        "importClosurePathCount": len(imports),
        "absoluteImportClosureScanPathCount": len(absolute_scan_paths),
        "absolutePathExemptionCount": len(used_exemptions),
        "assetCount": len(asset_by_path),
        "dynamicRuntime": dynamic_report,
        "untrackedRequiredCount": len(unique_untracked),
        "untrackedRequired": unique_untracked,
        "errors": unique_errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not unique_errors else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BaselineError, json.JSONDecodeError, OSError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "FAIL_M0_BASELINE_VALIDATOR", "error": str(error)}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
