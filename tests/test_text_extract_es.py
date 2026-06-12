"""
Regression tests for the shared Spanish-text extraction primitives
(scripts/_text_extract_es.py) and the incident-class guard
(scripts/_harvest_base.py:validate_incident_class).

Every case here pins a fix from the 2026-06-12 adversarial review:
  * extract_status — deceased detection + 'hallar' resolution (was: deceased
    mis-mapped to resolved_alive; 'hallada' fell through to active).
  * extract_age — relative-time phrases ('hace 5 años') no longer read as age.
  * extract_municipio — ambiguous common-word names (Florida/Salinas/Dorado)
    only match when location-cue-anchored.
  * validate_incident_class — out-of-vocab class raises (the guard used to be
    unreachable dead code).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts._harvest_base import VALID_INCIDENT_CLASSES, validate_incident_class  # noqa: E402
from scripts._text_extract_es import (  # noqa: E402
    extract_age,
    extract_municipio,
    extract_status,
)


@pytest.fixture(autouse=True)
def _deterministic_seed():
    yield


# ---------------------------------------------------------------- extract_status

@pytest.mark.parametrize("text,expected", [
    ("Fue encontrado fallecido.", "resolved_deceased"),
    ("encontrado muerto", "resolved_deceased"),
    ("hallada sin vida", "resolved_deceased"),
    ("se identificaron sus restos mortales", "resolved_deceased"),
    ("fue hallada sana y salva", "resolved_alive"),
    ("Persona localizada en buenas condiciones", "resolved_alive"),
    ("apareció con vida", "resolved_alive"),
    ("Estado: RESUELTO", "resolved_alive"),
    ("Estado: ACTIVO", "active"),
    ("Desaparecida desde el 3 de marzo", "active"),
    ("", "active"),
])
def test_extract_status(text, expected):
    assert extract_status(text) == expected


def test_deceased_wins_over_alive_verb():
    # 'encontrado' alone is alive; 'encontrado fallecido' must be deceased.
    assert extract_status("encontrado") == "resolved_alive"
    assert extract_status("encontrado fallecido") == "resolved_deceased"


# ---------------------------------------------------------------- extract_age

@pytest.mark.parametrize("text,expected", [
    ("Edad: 28 años", "28"),
    ("Edad: 9 años", "9"),
    ("Tiene unos 40 años", "40"),               # legit unlabeled age
    ("Desaparecio hace 5 años en Ponce", ""),   # relative time → not age
    ("lleva 3 años desaparecida", ""),
    ("Reportada desaparecida desde hace 8 años", ""),
    ("Edad: desconocida. desaparecido hace 8 años", ""),
])
def test_extract_age(text, expected):
    assert extract_age(text) == expected


# ---------------------------------------------------------------- extract_municipio

@pytest.mark.parametrize("text,expected", [
    # Ambiguous names must NOT match bare (common-word false positives).
    ("Se mudo a Florida, Estados Unidos", ""),
    ("compro sal en las salinas de Cabo Rojo", "Cabo Rojo"),  # Cabo Rojo wins via cue
    ("llevaba un reloj dorado", ""),
    ("cabello dorado y ojos verdes", ""),
    # Ambiguous names match WHEN location-cue-anchored.
    ("visto por ultima vez en Florida", "Florida"),
    ("municipio de Dorado", "Dorado"),
    ("residente de Salinas", "Salinas"),
    # Unambiguous names match bare or cued.
    ("Última vez vista en San Juan", "San Juan"),
    ("cerca del Hospital Damas, Ponce", "Ponce"),
    ("desaparecido en Carolina el 2024", "Carolina"),
    # San Juan beats the (non-municipio) bare token 'Juan'.
    ("Juan fue visto en San Juan", "San Juan"),
    ("", ""),
])
def test_extract_municipio(text, expected):
    assert extract_municipio(text) == expected


# ---------------------------------------------------------------- validate_incident_class

def test_validate_incident_class_accepts_known():
    for cls in VALID_INCIDENT_CLASSES:
        assert validate_incident_class(cls) == cls


def test_validate_incident_class_allows_empty():
    # Empty is allowed — some sources legitimately leave it blank.
    assert validate_incident_class("") == ""


def test_validate_incident_class_rejects_typo():
    with pytest.raises(ValueError, match="unknown incident_class"):
        validate_incident_class("endangerd_adult")  # typo
    with pytest.raises(ValueError):
        validate_incident_class("not_a_real_class")
