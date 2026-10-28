"""Offline checks for repair(): bookkeeping errors are fixed, safety errors still fail."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import semantic_core as core
REG={'version':'v1','rules':list(core.OWNER_RULES)+[{'rule_id':'scenario.S1','source_id':'sheet:s1'}]}
REFS={'m1','m2'}
def answer(**over):
    base={'summary':'Клиент спрашивает о пробном','intents':['пробное'],'entities':[],'known_information':[],'missing_information':[],'rule_ids':['scenario.S1'],'source_ids':['sheet:s1'],'required_actions':['ask_customer'],'decision':'clarify','reason':'нет класса','policy_version':'v1','draft':'Подскажите, в каком классе ребёнок?','claims':[]}
    base.update(over);return base
def run(result):
    fixed,notes=core.repair(result,REG,REFS)
    try:return core.validate(fixed,REG,REFS),notes
    except core.AgentError as e:
        if str(e)!='MODEL_SCENARIO_REQUIRED':raise
        return core.validate(dict(fixed,decision='knowledge_gap'),REG,REFS),notes
class Repair(unittest.TestCase):
    def test_clean_answer_unchanged(self):
        out,notes=run(answer());self.assertEqual(notes,[]);self.assertEqual(out['rule_ids'],['scenario.S1'])
    def test_unknown_rule_dropped(self):
        out,notes=run(answer(rule_ids=['scenario.S1','scenario.NOPE'],source_ids=['sheet:s1','x']));self.assertEqual(out['rule_ids'],['scenario.S1']);self.assertTrue(notes)
    def test_entity_with_bad_ref_dropped(self):
        out,_=run(answer(entities=[{'name':'класс','value':'5','origin':'client_reported','evidence_ref':'m9'},{'name':'класс','value':'5','origin':'client_reported','evidence_ref':'m1'}]));self.assertEqual(len(out['entities']),1)
    def test_claim_with_unknown_source_dropped(self):
        out,notes=run(answer(claims=[{'text':'x','kind':'rule','refs':['sheet:zz']}]));self.assertEqual(out['claims'],[]);self.assertTrue(notes)
    def test_missing_scenario_keeps_draft_with_note(self):
        out,notes=run(answer(rule_ids=[],source_ids=[]));self.assertTrue(out['draft']);self.assertTrue(any('сценарий' in n for n in notes))
    def test_policy_version_restored(self):
        run(answer(policy_version='old'))
    def test_unknown_action_dropped(self):
        out,_=run(answer(required_actions=['ask_customer','send_money']));self.assertEqual(out['required_actions'],['ask_customer'])
    def test_safety_checks_still_fail(self):
        for bad,code in [({'draft':'Стоимость 4500 руб в месяц'},'MODEL_PRICE_UNVERIFIED'),({'draft':'Я записала вас на пробное'},'MODEL_ACTION_NOT_EXECUTED'),({'claims':[{'text':'оплачено','kind':'system_fact','refs':['m1']}]},'MODEL_UNSUPPORTED_CLAIM'),({'draft':'Пишите на a@b.ru'},'MODEL_CONTACT_LEAK')]:
            with self.assertRaises(core.AgentError) as ctx:run(answer(**bad))
            self.assertEqual(str(ctx.exception),code)
    def test_schema_errors_still_fail(self):
        with self.assertRaises(core.AgentError):run({'summary':'x'})
if __name__=='__main__':unittest.main()
