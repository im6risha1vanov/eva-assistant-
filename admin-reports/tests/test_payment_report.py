import json
import sqlite3
import unittest
from unittest.mock import Mock, patch

import semantic_core as core
import worker


def outbound(text, attachment=False):
    return {'ref':'prior','role':'outbound_author_unverified','text':text,'attachment_unknown':attachment}


class PaymentReportTest(unittest.TestCase):
    def run_report(self, text, history=(), *, model_draft='Спасибо, поняла.',
                   model_summary='Клиент ответил.', decision='draft_answer', attachment=False, human=False,
                   verified_facts=None):
        db=sqlite3.connect(':memory:')
        db.row_factory=sqlite3.Row
        self.addCleanup(db.close)
        db.executescript(worker.SCHEMA)
        db.execute("INSERT INTO reports(event_key,source_id,status) VALUES ('sample',1,'pending')")
        db.commit()
        current={'ref':'sample','role':'client_reported','text':text,'attachment_unknown':attachment}
        data={'text':text}
        job={'event_key':'sample','source_id':1,'input_json':json.dumps(data)}
        reg={'version':'test','rules':[{'rule_id':'scenario.test','source_id':'test.source'}]}
        result={k:[] for k in core.FIELDS}
        result.update(summary=model_summary,reason='Тест',draft=model_draft,decision=decision,
                      policy_version='test',rule_ids=['scenario.test'],source_ids=['test.source'])
        provider=Mock()
        provider.request.return_value=(result,'test-call')
        with (patch.object(worker,'connect',return_value=Mock()),
              patch.object(worker.Path,'exists',return_value=False),
              patch.object(worker,'context',return_value=(data,current,history,human)),
              patch.object(core,'read_regulation',return_value=reg),
              patch.object(core,'atomic')):
            if verified_facts is not None:
                payload={'conversation':[current,*history],'verified_facts':verified_facts}
                with patch.object(core.Engine,'payload',return_value=payload):
                    worker.analyse(db,job,{'recipients':[1]},provider)
            else:
                worker.analyse(db,job,{'recipients':[1]},provider)
        self.assertEqual(provider.request.call_count,1)
        report=db.execute('SELECT status,summary,draft,error FROM reports').fetchone()
        delivery=db.execute('SELECT body,status FROM deliveries').fetchone()
        self.assertEqual(delivery['status'],'pending')
        self.assertIn(report['draft'],delivery['body'])
        return report,delivery['body']

    def test_payment_method_reply_adds_visible_check_without_claiming_credit(self):
        for question in ('Подскажите, как вы оплатили: по ссылке или по реквизитам?',
                         'Вы оплачивали по реквизитам или по ссылке, которую мы выше направляли?'):
            with self.subTest(question=question):
                report,body=self.run_report('По ссылке.',[outbound(question)])
                self.assertEqual(report['status'],'ready')
                self.assertEqual(report['draft'],'Спасибо, сверим оплату.')
                self.assertIn('Что проверить: Проверить поступление платежа.',body)

    def test_explicit_past_payment_and_manual_control(self):
        report,body=self.run_report('Да, я уже оплатила по ссылке!',human=True)
        self.assertEqual(report['draft'],'Спасибо, сверим оплату.')
        self.assertIn('Проверить поступление платежа.',body)
        self.assertIn('управление остаётся у сотрудника',body)

    def test_invoice_dispute_prescribes_plan_check_before_question(self):
        report,body=self.run_report('В счёте больше занятий, чем мы планировали.',
                                    model_draft='Скажите, какие занятия планировали?')
        self.assertEqual(report['draft'],'Сверим, какие занятия вошли в счёт, и напишем.')
        self.assertIn('Что проверить: Сверить занятия в счёте с планом занятий.',body)

    def test_new_link_request_is_not_payment_report(self):
        report,body=self.run_report('Пришлите ссылку на оплату.',
                                    [outbound('Как оплачивали?')],
                                    model_draft='Пришлём ссылку на оплату.')
        self.assertEqual(report['draft'],'Пришлём ссылку на оплату.')
        self.assertNotIn('Что проверить:',body)

    def test_ambiguous_and_multi_topic_replies_keep_the_validated_draft(self):
        question=outbound('Как оплачивали?')
        for text,history,attachment in [
            ('По ссылке.',[],False),
            ('По ссылке.',[question,outbound('Как удобнее оплатить?')],False),
            ('По ссылке.',[question],True),
            ('Оплачу по ссылке.',[question],False),
            ('Не оплатила по ссылке.',[question],False),
            ('Оплатила по ссылке. Можно перенести урок?',[question],False),
        ]:
            with self.subTest(text=text,history=history,attachment=attachment):
                report,body=self.run_report(text,history,attachment=attachment)
                self.assertEqual(report['draft'],'Спасибо, поняла.')
                self.assertNotIn('Что проверить:',body)

    def test_verified_facts_prevent_fallback(self):
        report,body=self.run_report('Оплатил по ссылке.',verified_facts=[{'status':'settled'}],
                                    model_draft='Спасибо.')
        self.assertEqual(report['draft'],'Спасибо.')
        self.assertNotIn('Что проверить:',body)

    def test_technical_incident_is_not_replaced(self):
        report,body=self.run_report('Оплатил по ссылке.',decision='technical_incident',
                                    model_draft='Нужна проверка.')
        self.assertEqual(report['draft'],'Нужна проверка.')
        self.assertNotIn('Что проверить:',body)

    def test_unsafe_model_output_is_not_rescued_by_payment_override(self):
        report,body=self.run_report('Оплатил по ссылке.',model_draft='В счёте 9876 ₽.')
        self.assertEqual(report['status'],'failed')
        self.assertEqual(report['error'],'MODEL_PRICE_UNVERIFIED')
        self.assertNotIn('9876',body)
        self.assertNotIn('Что проверить:',body)
