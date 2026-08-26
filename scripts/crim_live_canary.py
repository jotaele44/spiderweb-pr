#!/usr/bin/env python3
from __future__ import annotations

import json

from integration.crim_lookup import (
    CrimClient,
    CrimLookup,
    IdentityState,
    LookupMode,
    LookupState,
    validate_layer_metadata,
)


def main() -> int:
    client = CrimClient()
    metadata, _ = client.metadata()
    validate_layer_metadata(metadata)

    # A negative OBJECTID should be a valid zero result while still exercising
    # live query transport and ArcGIS response decoding.
    zero = CrimLookup(client).identifier(
        LookupMode.OBJECTID,
        "-1",
        return_geometry=False,
    )
    if (
        zero.state != LookupState.VALID_ZERO_RESULT
        or zero.identity_state != IdentityState.CANDIDATE_NOT_IDENTITY
        or zero.match_count != 0
        or zero.candidates
    ):
        raise RuntimeError(
            "negative OBJECTID canary did not produce a valid zero result"
        )

    print(
        json.dumps(
            {
                "contract": "PASS",
                "valid_zero_canary": "PASS",
                "layer": metadata.get("name"),
                "currentVersion": metadata.get("currentVersion"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
