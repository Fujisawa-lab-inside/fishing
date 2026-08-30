from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/stage20_local_observation_intake_validate_only_authority_v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_template() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text())
    if contract.get("status") != "TEMPLATE_ONLY_NOT_AUTHORIZED_NO_INPUT_FILES":
        raise ValueError("local observation intake authority template status changed")
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        if not path.is_file() or sha256(path) != binding["sha256"]:
            raise ValueError(f"local observation authority binding mismatch: {binding['path']}")
    if len(contract["permittedActions"]) != 7:
        raise ValueError("validate-only scope changed")
    required_forbidden = {
        "invent or impute missing values",
        "parameter fitting or coefficient selection",
        "numerical solver execution",
        "YODA connection, transfer, activation, or launch",
        "GUI integration or promotion",
        "git push or release",
    }
    if not required_forbidden.issubset(set(contract["forbiddenActions"])):
        raise ValueError("validate-only prohibitions weakened")
    boundary = contract["decisionBoundary"]
    for key, value in boundary.items():
        if key != "templateValidationPermitted" and value:
            raise ValueError(f"unissued intake capability enabled: {key}")
    template = contract["template"]
    if template["authorizationId"] is not None or template["sourceBundleInventory"] or template["freshQuarantineRoot"] is not None:
        raise ValueError("authority template unexpectedly populated")
    return {
        "status": "PASS_TEMPLATE_ONLY_NO_AUTHORITY",
        "permittedActionCount": len(contract["permittedActions"]),
        "forbiddenActionCount": len(contract["forbiddenActions"]),
        "authorityIssued": False,
        "inputFileCount": 0,
        "quarantineCreationCount": 0,
        "fileCopyCount": 0,
        "solverRunCount": 0,
        "yodaConnectionCount": 0,
        "releaseAuthorized": False,
    }


if __name__ == "__main__":
    print(json.dumps(validate_template(), indent=2, sort_keys=True))
