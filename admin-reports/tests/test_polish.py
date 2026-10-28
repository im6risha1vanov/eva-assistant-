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
    def test_labels_are_stable_and_restored(self):
        names={}
        a=core.redact('Это Анна, Миша заболел',names);b=core.redact('Мишу приведу в четверг',names)
        self.assertNotIn('Миш',a+b);self.assertEqual(a.count('[имя'),2);self.assertEqual(b,names['Миш']+'у приведу в четверг')
        draft,notes=core.restore(names['Анн']+'а, выздоравливайте, ждём '+names['Миш']+'у в четверг',names)
        self.assertEqual(draft,'Анна, выздоравливайте, ждём Мишу в четверг');self.assertEqual(notes,[])
    def test_case_forms_share_one_label(self):
        names={};core.redact('Ксения',names);core.redact('Ксению',names);core.redact('Иван',names);core.redact('Ивану',names)
        self.assertEqual(sorted(names),['Иван','Ксени'])
    def test_unknown_label_flagged(self):
        self.assertEqual(core.restore('Ждём [имя7]',{})[1],['имя не подставлено'])
    def test_legacy_redact_unchanged(self):
        self.assertEqual(core.redact('Привет, Анна'),'Привет, [лицо]')
class Ordinary(unittest.TestCase):
    def test_sentence_start_words_are_not_names(self):
        names={};text=core.redact('При оплате пришлите ссылку. Ждём ответа. Маша заболела',names)
        self.assertIn('При оплате',text);self.assertIn('Ждём',text);self.assertEqual(list(names),['Маш'])
    def test_word_seen_lowercase_is_not_a_name(self):
        names={};self.assertEqual(core.redact('Сквозняк в классе',names,frozenset({'сквозняк'})),'Сквозняк в классе');self.assertEqual(names,{})
if __name__=='__main__':unittest.main()
