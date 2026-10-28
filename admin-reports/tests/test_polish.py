"""Offline checks for polish(): messenger punctuation and template-phrase flags."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import semantic_core as core
class Polish(unittest.TestCase):
    def test_dash_replaced(self):
        self.assertEqual(core.polish('Занятие в 18:00 — в офисе')[0],'Занятие в 18:00 - в офисе')
    def test_exclamations_collapsed(self):
        self.assertEqual(core.polish('Хорошо. Ждём вас!!!')[0],'Хорошо. Ждём вас!')
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
class Greeting(unittest.TestCase):
    def test_unprompted_greeting_dropped(self):
        self.assertEqual(core.polish('Здравствуйте! Пришлём ссылку на оплату.','+')[0],'Пришлём ссылку на оплату.')
    def test_greeting_back_kept(self):
        self.assertEqual(core.polish('Добрый вечер. Ждём в четверг.','Добрый вечер, придём')[0],'Добрый вечер. Ждём в четверг.')
    def test_opening_exclamation_softened(self):
        self.assertEqual(core.polish('Пожалуйста! Ждём вас.','Спасибо')[0],'Пожалуйста. Ждём вас.')
class Actions(unittest.TestCase):
    def test_fixed_wording_counts_as_done_action(self):
        reg={'version':'v1','rules':[{'rule_id':'scenario.S1','source_id':'s1'}]}
        r={'summary':'a','intents':[],'entities':[],'known_information':[],'missing_information':[],'rule_ids':['scenario.S1'],'source_ids':['s1'],'required_actions':[],'decision':'clarify','reason':'r','policy_version':'v1','draft':'Зафиксировали цель занятий','claims':[]}
        with self.assertRaises(core.AgentError) as ctx:core.validate(r,reg,set())
        self.assertEqual(str(ctx.exception),'MODEL_ACTION_NOT_EXECUTED')
if __name__=='__main__':unittest.main()
