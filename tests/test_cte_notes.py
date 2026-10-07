import unittest

from cte_notes import format_cte_notes


class CteNotesTests(unittest.TestCase):
    def test_monthly_without_penalty(self):
        self.assertEqual(
            format_cte_notes("Mensile", "Nessuna penale rilevata"),
            "Fatturazione: Mensile\nRecesso anticipato: Nessuna penale rilevata",
        )

    def test_bimonthly_with_explicit_early_withdrawal_cost(self):
        self.assertEqual(
            format_cte_notes("Bimestrale", "€120 in caso di recesso entro 12 mesi"),
            "Fatturazione: Bimestrale\nRecesso anticipato: €120 in caso di recesso entro 12 mesi",
        )

    def test_missing_values_are_not_invented(self):
        self.assertEqual(
            format_cte_notes(None, None),
            "Fatturazione: Non indicata\nRecesso anticipato: Non indicato",
        )

    def test_existing_notes_are_preserved_after_standard_lines(self):
        self.assertEqual(
            format_cte_notes("Mensile", "Non indicato", "Domiciliazione bancaria", "Durata minima 12 mesi"),
            "Fatturazione: Mensile\nRecesso anticipato: Non indicato\n"
            "Altre note: Domiciliazione bancaria; Durata minima 12 mesi",
        )


if __name__ == "__main__":
    unittest.main()
