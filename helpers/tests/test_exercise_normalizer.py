"""
Tests for helpers/exercise_normalizer.py — pure functions, no I/O.

The mapping cache and the save function are both patched so tests never
touch the real exercise_mapping.json file on disk.
"""
import pytest
from unittest.mock import patch
from helpers.exercise_normalizer import normalize_exercise_name, normalize_exercises
import helpers.exercise_normalizer as normalizer_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_MAPPING = {
    "Peso muerto con mancuernas":         "Peso muerto con mancuernas",
    "Tirón dorsal en polea agarre prono": "Tirón dorsal en polea (agarre prono)",
    "Abdominales bolita a dos piernas":   "Abdominal bolita a dos piernas",
}


@pytest.fixture(autouse=True)
def patch_mapping(monkeypatch):
    """
    Replace the in-memory cache with a small controlled dict and stub out the
    file-write function so no test ever touches exercise_mapping.json on disk.
    The mapping is deep-copied per test so mutations in one test do not bleed
    into the next.
    """
    monkeypatch.setattr(normalizer_mod, "_mapping", dict(FAKE_MAPPING))
    monkeypatch.setattr(normalizer_mod, "_save_mapping", lambda m: None)


# ---------------------------------------------------------------------------
# normalize_exercise_name — mapping lookup
# ---------------------------------------------------------------------------

class TestNormalizeExerciseNameMapping:
    def test_mapped_name_returns_canonical(self):
        result = normalize_exercise_name("Tirón dorsal en polea agarre prono")
        assert result == "Tirón dorsal en polea (agarre prono)"

    def test_mapping_with_same_value_returns_same(self):
        result = normalize_exercise_name("Peso muerto con mancuernas")
        assert result == "Peso muerto con mancuernas"

    def test_mapped_name_not_processed_by_auto_format(self):
        # The mapping value is returned as-is — auto-format must NOT be applied on top,
        # even if the raw name would match a formatting rule.
        result = normalize_exercise_name("Abdominales bolita a dos piernas")
        assert result == "Abdominal bolita a dos piernas"


# ---------------------------------------------------------------------------
# normalize_exercise_name — auto-format fallback
# ---------------------------------------------------------------------------

class TestNormalizeExerciseNameAutoFormat:
    def test_unmapped_name_returned_unchanged_when_no_rules_apply(self):
        result = normalize_exercise_name("Sentadilla búlgara")
        assert result == "Sentadilla búlgara"

    def test_empuje_prefix_becomes_press(self):
        result = normalize_exercise_name("Empuje de hombros con barra")
        assert result == "Press de hombros con barra"

    def test_empuje_only_replaced_at_start(self):
        # "Empuje" mid-name must not be replaced
        result = normalize_exercise_name("Fuerza de empuje lateral")
        assert result == "Fuerza de empuje lateral"

    def test_con_agarre_becomes_parenthesised(self):
        result = normalize_exercise_name("Remo con agarre neutro")
        assert result == "Remo (agarre neutro)"

    def test_agarre_at_end_becomes_parenthesised(self):
        result = normalize_exercise_name("Bíceps con barra agarre supino")
        assert result == "Bíceps con barra (agarre supino)"

    def test_en_banco_plano_becomes_parenthesised(self):
        result = normalize_exercise_name("Press de pecho en banco plano")
        assert result == "Press de pecho (banco plano)"

    def test_en_banco_inclinado_becomes_parenthesised(self):
        result = normalize_exercise_name("Press con mancuernas en banco inclinado")
        assert result == "Press con mancuernas (banco inclinado)"

    def test_banco_qualifier_is_case_insensitive(self):
        # The regex matches case-insensitively; "banco" is lowercase in the replacement literal,
        # while the captured group (\1) preserves the original casing.
        result = normalize_exercise_name("Press en Banco Plano")
        assert result == "Press (banco Plano)"

    def test_trailing_sentado_becomes_parenthesised(self):
        result = normalize_exercise_name("Press de hombros con barra sentado")
        assert result == "Press de hombros con barra (sentado)"

    def test_trailing_sentado_case_insensitive(self):
        # The regex matches case-insensitively but the replacement literal is always "(sentado)".
        result = normalize_exercise_name("Curl con barra Sentado")
        assert result == "Curl con barra (sentado)"

    def test_sentado_in_middle_not_parenthesised(self):
        # Only trailing "sentado" gets parenthesised
        result = normalize_exercise_name("Press sentado con barra")
        assert result == "Press sentado con barra"

    def test_empuje_and_banco_rules_both_applied(self):
        # Empuje→Press applies first, then the banco rule
        result = normalize_exercise_name("Empuje de pecho en banco inclinado")
        assert result == "Press de pecho (banco inclinado)"


# ---------------------------------------------------------------------------
# normalize_exercise_name — unmapped entry auto-creation
# ---------------------------------------------------------------------------

class TestUnmappedAutoCreate:
    def test_unmapped_name_is_added_to_mapping(self):
        """After normalizing an unknown name, it must appear in the in-memory mapping."""
        normalize_exercise_name("Ejercicio completamente nuevo")
        assert "Ejercicio completamente nuevo" in normalizer_mod._mapping

    def test_unmapped_entry_has_auto_formatted_canonical(self):
        normalize_exercise_name("Empuje de piernas en máquina")
        assert normalizer_mod._mapping["Empuje de piernas en máquina"] == "Press de piernas en máquina"

    def test_unmapped_triggers_save(self, monkeypatch):
        """_save_mapping must be called exactly once for each new entry."""
        calls = []
        monkeypatch.setattr(normalizer_mod, "_save_mapping", lambda m: calls.append(m))
        normalize_exercise_name("Ejercicio sin mapping")
        assert len(calls) == 1

    def test_unmapped_prints_warning(self, capsys):
        normalize_exercise_name("Ejercicio sin mapping")
        err = capsys.readouterr().err
        assert "UNMAPPED" in err
        assert "Ejercicio sin mapping" in err

    def test_already_mapped_does_not_trigger_save(self, monkeypatch):
        """A name already in the mapping must NOT call _save_mapping."""
        calls = []
        monkeypatch.setattr(normalizer_mod, "_save_mapping", lambda m: calls.append(m))
        normalize_exercise_name("Peso muerto con mancuernas")   # already in FAKE_MAPPING
        assert calls == []

    def test_second_call_with_same_unknown_name_does_not_save_again(self, monkeypatch):
        """Once an entry is in the mapping, subsequent calls must skip the save."""
        calls = []
        monkeypatch.setattr(normalizer_mod, "_save_mapping", lambda m: calls.append(m))
        normalize_exercise_name("Ejercicio nuevo repetido")
        normalize_exercise_name("Ejercicio nuevo repetido")
        assert len(calls) == 1   # saved only on the first call


# ---------------------------------------------------------------------------
# normalize_exercises
# ---------------------------------------------------------------------------

class TestNormalizeExercises:
    def test_modifies_name_field_in_place(self):
        exercises = [{"name": "Empuje de pecho en banco plano", "is_comb": False}]
        normalize_exercises(exercises)
        assert exercises[0]["name"] == "Press de pecho (banco plano)"

    def test_returns_same_list_object(self):
        exercises = [{"name": "Sentadilla"}]
        result = normalize_exercises(exercises)
        assert result is exercises

    def test_empty_list_returns_empty(self):
        assert normalize_exercises([]) == []

    def test_other_fields_are_not_modified(self):
        ex = {"name": "Empuje lateral", "is_comb": True, "week_reps": [[10, 10, 10]]}
        normalize_exercises([ex])
        assert ex["is_comb"] is True
        assert ex["week_reps"] == [[10, 10, 10]]

    def test_multiple_exercises_all_normalized(self):
        exercises = [
            {"name": "Empuje de pecho en banco plano"},
            {"name": "Sentadilla clásica"},
        ]
        normalize_exercises(exercises)
        assert exercises[0]["name"] == "Press de pecho (banco plano)"
        assert exercises[1]["name"] == "Sentadilla clásica"


# ---------------------------------------------------------------------------
# normalize_exercise_name — mapping lookup
# ---------------------------------------------------------------------------

class TestNormalizeExerciseNameMapping:
    def test_mapped_name_returns_canonical(self):
        result = normalize_exercise_name("Tirón dorsal en polea agarre prono")
        assert result == "Tirón dorsal en polea (agarre prono)"

    def test_mapping_with_same_value_returns_same(self):
        result = normalize_exercise_name("Peso muerto con mancuernas")
        assert result == "Peso muerto con mancuernas"

    def test_mapped_name_not_processed_by_auto_format(self):
        # The mapping value is returned as-is — auto-format must NOT be applied on top,
        # even if the raw name would match a formatting rule.
        result = normalize_exercise_name("Abdominales bolita a dos piernas")
        assert result == "Abdominal bolita a dos piernas"


# ---------------------------------------------------------------------------
# normalize_exercise_name — auto-format fallback
# ---------------------------------------------------------------------------

class TestNormalizeExerciseNameAutoFormat:
    def test_unmapped_name_returned_unchanged_when_no_rules_apply(self):
        result = normalize_exercise_name("Sentadilla búlgara")
        assert result == "Sentadilla búlgara"

    def test_empuje_prefix_becomes_press(self):
        result = normalize_exercise_name("Empuje de hombros con barra")
        assert result == "Press de hombros con barra"

    def test_empuje_only_replaced_at_start(self):
        # "Empuje" mid-name must not be replaced
        result = normalize_exercise_name("Fuerza de empuje lateral")
        assert result == "Fuerza de empuje lateral"

    def test_con_agarre_becomes_parenthesised(self):
        result = normalize_exercise_name("Remo con agarre neutro")
        assert result == "Remo (agarre neutro)"

    def test_agarre_at_end_becomes_parenthesised(self):
        result = normalize_exercise_name("Bíceps con barra agarre supino")
        assert result == "Bíceps con barra (agarre supino)"

    def test_en_banco_plano_becomes_parenthesised(self):
        result = normalize_exercise_name("Press de pecho en banco plano")
        assert result == "Press de pecho (banco plano)"

    def test_en_banco_inclinado_becomes_parenthesised(self):
        result = normalize_exercise_name("Press con mancuernas en banco inclinado")
        assert result == "Press con mancuernas (banco inclinado)"

    def test_banco_qualifier_is_case_insensitive(self):
        # The regex matches case-insensitively; "banco" is lowercase in the replacement literal,
        # while the captured group (\1) preserves the original casing.
        result = normalize_exercise_name("Press en Banco Plano")
        assert result == "Press (banco Plano)"

    def test_trailing_sentado_becomes_parenthesised(self):
        result = normalize_exercise_name("Press de hombros con barra sentado")
        assert result == "Press de hombros con barra (sentado)"

    def test_trailing_sentado_case_insensitive(self):
        # The regex matches case-insensitively but the replacement literal is always "(sentado)".
        result = normalize_exercise_name("Curl con barra Sentado")
        assert result == "Curl con barra (sentado)"

    def test_sentado_in_middle_not_parenthesised(self):
        # Only trailing "sentado" gets parenthesised
        result = normalize_exercise_name("Press sentado con barra")
        assert result == "Press sentado con barra"

    def test_empuje_and_banco_rules_both_applied(self):
        # Empuje→Press applies first, then the banco rule
        result = normalize_exercise_name("Empuje de pecho en banco inclinado")
        assert result == "Press de pecho (banco inclinado)"


# ---------------------------------------------------------------------------
# normalize_exercises
# ---------------------------------------------------------------------------

class TestNormalizeExercises:
    def test_modifies_name_field_in_place(self):
        exercises = [{"name": "Empuje de pecho en banco plano", "is_comb": False}]
        normalize_exercises(exercises)
        assert exercises[0]["name"] == "Press de pecho (banco plano)"

    def test_returns_same_list_object(self):
        exercises = [{"name": "Sentadilla"}]
        result = normalize_exercises(exercises)
        assert result is exercises

    def test_empty_list_returns_empty(self):
        assert normalize_exercises([]) == []

    def test_other_fields_are_not_modified(self):
        ex = {"name": "Empuje lateral", "is_comb": True, "week_reps": [[10, 10, 10]]}
        normalize_exercises([ex])
        assert ex["is_comb"] is True
        assert ex["week_reps"] == [[10, 10, 10]]

    def test_multiple_exercises_all_normalized(self):
        exercises = [
            {"name": "Empuje de pecho en banco plano"},
            {"name": "Sentadilla clásica"},
        ]
        normalize_exercises(exercises)
        assert exercises[0]["name"] == "Press de pecho (banco plano)"
        assert exercises[1]["name"] == "Sentadilla clásica"
