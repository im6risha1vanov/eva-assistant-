import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import worker


QUESTION='Есть ли место в группе по математике на Интернациональной во вторник в 18:00?'
NOW=datetime(2026,11,4,18,tzinfo=worker.CRM_MOSCOW)


def fixture():
    return {
        'status':'ok','fetched_epoch':NOW.timestamp()-173,
        'branches':[{'branch':'Интернациональная','groups':[{
            'subjects':['Математика'],'class':7,'exam':None,
            'schedule':[{'day':'вторник','time':'18:00'}],
            'availability_status':'known',
            'next_lesson':{'date':'2026-11-10','time':'18:00','subject':'Математика',
                           'capacity':8,'occupied':6,'free_places':2},
        }]}],
    }


class CrmAvailabilityTest(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path=Path(directory.name,'current.json')
        self.data=fixture()

    def lookup(self,text=QUESTION):
        self.path.write_text(json.dumps(self.data),encoding='utf-8')
        return worker.crm_group_availability(text,now=NOW,path=self.path)

    def test_exact_future_slot_adds_verified_fact_to_draft_and_admin_summary(self):
        availability=self.lookup()
        self.assertIsNotNone(availability)
        with patch.object(worker,'crm_group_availability',return_value=availability):
            summary,draft=worker.report_text(
                {'decision':'clarify','summary':'Вопрос о месте.','draft':'Уточним.'},
                {'text':QUESTION},[],[],False,[])
        self.assertIn('По свежей сводке AlfaCRM',summary)
        self.assertIn('10.11 в 18:00',draft)
        self.assertIn('свободно 2 места',draft)
        self.assertNotIn('запис',draft.lower())

    def test_zeros_are_distinct_from_unknown_counts(self):
        lesson=self.data['branches'][0]['groups'][0]['next_lesson']
        lesson.update(occupied=8,free_places=0)
        self.assertIn('нет свободных мест',worker.crm_availability_text(*self.lookup())[1])
        for bad in (None,True,1):
            with self.subTest(bad=bad):
                lesson['free_places']=bad
                self.assertIsNone(self.lookup())

    def test_stale_future_and_error_snapshots_are_rejected(self):
        for age,status in [(301,'ok'),(-1,'ok'),(20,'error')]:
            with self.subTest(age=age,status=status):
                self.data.update(fetched_epoch=NOW.timestamp()-age,status=status)
                self.assertIsNone(self.lookup())

    def test_an_unknown_second_group_blocks_an_apparently_unique_match(self):
        groups=self.data['branches'][0]['groups']
        other=copy.deepcopy(groups[0])
        other.update({'class':None,'availability_status':'unknown','next_lesson':None})
        groups.append(other)
        query=QUESTION.replace('по математике','по математике для 7 класса')
        self.assertIsNone(self.lookup(query))

    def test_different_earliest_lesson_does_not_prove_requested_slot(self):
        lesson=self.data['branches'][0]['groups'][0]['next_lesson']
        for field,value in [('date','2026-11-05'),('time','17:00'),('subject','Русский язык')]:
            with self.subTest(field=field):
                original=lesson[field]
                lesson[field]=value
                self.assertIsNone(self.lookup())
                lesson[field]=original

    def test_no_guessing_branch_format_or_booking_intent(self):
        for text in (QUESTION.replace('на Интернациональной ',''),
                     QUESTION.replace('на Интернациональной','онлайн на Интернациональной'),
                     QUESTION+' Запишите меня.',
                     QUESTION.replace('по математике','по математике огэ')):
            with self.subTest(text=text):
                self.assertIsNone(self.lookup(text))

    def test_manual_handoff_keeps_original_draft(self):
        with patch.object(worker,'crm_group_availability') as lookup:
            summary,draft=worker.report_text(
                {'decision':'human_handoff','summary':'Проверить вручную.','draft':'Посмотрим.'},
                {'text':QUESTION},[],[],True,[])
        lookup.assert_not_called()
        self.assertEqual(draft,'Посмотрим.')
        self.assertIn('управление остаётся у сотрудника',summary)
