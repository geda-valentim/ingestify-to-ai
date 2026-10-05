"""Project/folder name normalisation (spec 0004 § 4.1): display name vs key."""
import unicodedata

import pytest

from shared.projects import (
    MAX_KEY_LENGTH,
    MAX_NAME_LENGTH,
    InvalidNameError,
    clean_display_name,
    name_key,
    validate_name,
)


@pytest.mark.parametrize(
    "raw,display",
    [
        ("  Cliente   X  ", "Cliente X"),
        ("Reunião\tSemanal", "Reunião Semanal"),
        # NFD input is recomposed: same display string as typed in NFC
        (unicodedata.normalize("NFD", "Ação"), "Ação"),
    ],
)
def test_display_name_keeps_case_and_accents(raw, display):
    assert clean_display_name(raw) == display


@pytest.mark.parametrize(
    "raw,key",
    [
        ("Reunião", "reuniao"),
        ("Ação", "acao"),
        ("  reuniao   SEMANAL ", "reuniao semanal"),
        ("Straße", "strasse"),                    # casefold, not lower
        ("Tiếng Việt", "tieng viet"),              # stacked Latin accents
        ("Łódź", "łodz"),                          # ł does not decompose: stays
        ("Café Москва", "cafe москва"),            # mixed scripts
        ("ハード", "ハード"),                        # dakuten kept
        ("한국", "한국"),                            # Hangul recomposed
        ("x²", "x²"),                              # no compatibility mapping
        ("Æsir", "æsir"),                          # ligature letters intact
    ],
)
def test_key_table(raw, key):
    assert name_key(raw) == key


def test_equivalent_spellings_share_a_key():
    assert name_key("Reunião Semanal") == name_key("  reuniao   SEMANAL ")
    assert name_key(unicodedata.normalize("NFD", "Reunião")) == name_key("Reunião")


@pytest.mark.parametrize(
    "a,b",
    [
        ("ハード", "ハート"),     # dakuten is not an accent
        ("й", "и"),             # Cyrillic short i keeps its breve
        ("ё", "е"),             # Cyrillic yo keeps its diaeresis
        ("Łódź", "Lodz"),       # non-decomposable Latin letters stay distinct (D7)
        ("x²", "x2"),
        ("Ⅳ", "iv"),
        ("Œuvre", "oeuvre"),
        ("æ", "ae"),
    ],
)
def test_distinct_names_keep_distinct_keys(a, b):
    assert name_key(a) != name_key(b)


def test_hangul_key_is_composed_and_same_length():
    key = name_key("한국")
    assert key == unicodedata.normalize("NFC", key)
    assert len(key) == 2


def test_key_is_nfc():
    for raw in ("Ação", "ハード", "й", "Tiếng"):
        key = name_key(raw)
        assert key == unicodedata.normalize("NFC", key)


# --- validation --------------------------------------------------------------

def test_valid_name_returns_display_and_key():
    assert validate_name("  Cliente  X ") == ("Cliente X", "cliente x")


@pytest.mark.parametrize("raw", ["", "   ", None, "\t\n"])
def test_empty_is_rejected(raw):
    with pytest.raises(InvalidNameError, match="vazio"):
        validate_name(raw)


def test_too_long_display_is_rejected():
    validate_name("x" * MAX_NAME_LENGTH)
    with pytest.raises(InvalidNameError, match="100"):
        validate_name("x" * (MAX_NAME_LENGTH + 1))


def test_too_long_key_is_rejected():
    # "ﬃ" casefolds to "ffi": 100 display characters, 300 key characters
    raw = "ﬃ" * 100
    assert len(clean_display_name(raw)) == MAX_NAME_LENGTH
    with pytest.raises(InvalidNameError, match=str(MAX_KEY_LENGTH)):
        validate_name(raw)


@pytest.mark.parametrize("raw", ["a\x00b", "a\x07b", "a\x1bb", "a\x7fb"])
def test_control_characters_are_rejected(raw):
    with pytest.raises(InvalidNameError, match="controle"):
        validate_name(raw)


def test_slash_is_reserved_in_folder_names_only():
    assert validate_name("Contratos/2026", "project")[0] == "Contratos/2026"
    with pytest.raises(InvalidNameError, match="/"):
        validate_name("Contratos/2026", "folder")
