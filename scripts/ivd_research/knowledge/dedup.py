from __future__ import annotations

import re
from typing import Any


def normalize_title(title: str) -> str:
    value = re.sub(r"\s+", " ", str(title or "").lower()).strip()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", "", value)
    return value


def material_duplicate_keys(material: dict[str, Any]) -> list[str]:
    raw = material.get("raw_fields") or {}
    keys = []
    for label in ["pmid", "pmcid", "doi", "identifier", "nct_id", "uniprot_id"]:
        value = str(raw.get(label) or "").strip()
        if value:
            keys.append(f"{label}:{value.lower()}")
    for value in material.get("possible_duplicate_keys") or []:
        if value:
            keys.append(str(value).lower())
    title_key = normalize_title(material.get("title", ""))
    if title_key:
        keys.append(f"title:{title_key}")
    return sorted(set(keys))


def build_dedup_index(materials: list[dict[str, Any]]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for material in materials:
        material_id = str(material.get("material_id") or "")
        if not material_id:
            continue
        for key in material_duplicate_keys(material):
            index.setdefault(key, [])
            if material_id not in index[key]:
                index[key].append(material_id)
    return {key: ids for key, ids in index.items() if len(ids) > 1}

