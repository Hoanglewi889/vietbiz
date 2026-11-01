import os, tempfile, unittest, importlib.util
from pathlib import Path
p=Path(__file__).parents[1]/'server.py';spec=importlib.util.spec_from_file_location('vietbiz_server',p);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
class VietBizTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();s.DATA=Path(self.tmp.name);s.DB=s.DATA/'test.sqlite3';s.connect().close()
 def tearDown(self):self.tmp.cleanup()
 def test_cash(self):
  s.cash_create({'entry_date':'2026-10-31','kind':'income','amount_czk':200,'description':'Sales'});s.cash_create({'entry_date':'2026-10-31','kind':'expense','amount_czk':40,'description':'Goods'});self.assertEqual(s.overview()['cash_balance_czk'],160)
 def test_bad_cash(self):
  with self.assertRaises(ValueError):s.cash_create({'entry_date':'2026-10-31','kind':'expense','amount_czk':-1,'description':'No'})
 def test_shift(self):
  s.shift_create({'employee':'Lan','shift_date':'2026-10-31','start_time':'09:00','end_time':'18:00'});self.assertEqual(len(s.overview()['shifts']),1)
 def test_duplicate_document(self):
  import base64
  obj={'filename':'invoice.pdf','mime':'application/pdf','data_base64':base64.b64encode(b'%PDF-1.4\nmock').decode()};self.assertFalse(s.document_create(obj)['duplicate']);self.assertTrue(s.document_create(obj)['duplicate']);self.assertEqual(s.overview()['pending_documents'],1)
 def test_review(self):
  import base64
  id=s.document_create({'filename':'a.pdf','mime':'application/pdf','data_base64':base64.b64encode(b'%PDF-1.4\nmock').decode()})['id'];s.document_review({'id':id,'status':'approved','supplier':'Metro','amount_czk':150});self.assertEqual(s.overview()['pending_documents'],0)
if __name__=='__main__':unittest.main()
