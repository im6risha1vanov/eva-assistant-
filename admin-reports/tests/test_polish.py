"""Offline checks for polish(): messenger punctuation and template-phrase flags."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import semantic_core as core
class Polish(unittest.TestCase):
    def test_dash_replaced(self):
        self.assertEqual(core.polish('Занятие в 18:00 — в офисе')[0],'Занятие в 18:00 - в офисе')
    def test_exclamations_collapsed(self):
        self.assertEqual(core.polish('Ждём вас!!!')[0],'Ждём вас!')
    def test_template_flagged(self):
        draft,notes=core.polish('Хорошо. Если будут вопросы, обращайтесь')
        self.assertEqual(draft,'Хорошо. Если будут вопросы, обращайтесь');self.assertIn('обращайтесь',notes[0])
    def test_clean_draft_untouched(self):
        self.assertEqual(core.polish('Подскажите, в каком классе ребёнок?'),('Подскажите, в каком классе ребёнок?',[]))

class Names(unittest.TestCase):
    def test_names_kept_contacts_hidden(self):
        self.assertEqual(core.redact('Это Анна, мой номер +7 912 345 67 89',keep_names=True),'Это Анна, мой номер [номер]')
    def test_legacy_redact_unchanged(self):
        self.assertEqual(core.redact('Привет, Анна'),'Привет, [лицо]')
if __name__=='__main__':unittest.main()
