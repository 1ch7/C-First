import collections
import io
import json
import os
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.client import HTTPConnection
from unittest.mock import patch
import server
from server import pdf_bytes, email_bytes, public_roster

class ServerTests(unittest.TestCase):
    def test_pdf_has_real_pages_and_all_sections(self):
        raw = pdf_bytes({'goal': {'eventType': 'charity'}, 'drafts': []})
        self.assertTrue(raw.startswith(b'%PDF-1.4'))
        self.assertIn(b'/Type /Pages', raw)
        self.assertIn(b'SPONSOR SHORTLIST', raw)
        self.assertIn(b'VALIDATION AND OUTSTANDING', raw)
        self.assertTrue(raw.endswith(b'%%EOF\n'))
    def test_private_exports_disable_cache(self):
        for kind in ('application/json', 'application/pdf', 'message/rfc822'):
            with self.subTest(kind=kind):
                handler = object.__new__(server.Handler)
                handler.wfile = io.BytesIO()
                headers = {}
                handler.send_response = lambda code: None
                handler.send_header = lambda key, value: headers.update({key: value})
                handler.end_headers = lambda: None
                handler.response(200, {} if kind == 'application/json' else b'export', kind)
                self.assertEqual(headers['Cache-Control'], 'no-store')
    def test_empty_gmail_selection_makes_no_network_request(self):
        handler = object.__new__(server.Handler)
        with patch.object(server, 'row_run', return_value={'pack': {'drafts': [{'to': 'sponsorship@example.com'}]}}), patch.dict(os.environ, {'GOOGLE_CLIENT_ID': 'test-client'}), patch.object(server, 'urlopen') as network:
            with self.assertRaises(ValueError):
                handler.gmail('test-run', {'accessToken': 'mock-token', 'indices': []})
            network.assert_not_called()
    def test_blank_recipient_supported(self):
        raw = email_bytes({'subject': 'EventPilot draft', 'body': 'Proposed charity event', 'to': ''})
        self.assertNotIn(b'To:', raw)
        self.assertIn(b'Subject: EventPilot', raw)
    def test_roster_private_fields_removed(self):
        result = public_roster([{'name': 'Private Name', 'role': 'MC', 'email': 'private@example.com', 'freeDates': ['2027-03-20']}])
        self.assertNotEqual(result[0]['name'], 'Private Name')
        self.assertNotIn('email', result[0])
    def test_demo_explicit(self):
        result = public_roster([{'name': 'Demo MC', 'role': 'MC', 'demo': True, 'freeDates': []}])
        self.assertEqual(result[0]['name'], 'Demo MC #1')
        self.assertTrue(result[0]['demo'])
    def test_demo_flag_cannot_bypass_redaction(self):
        result = public_roster([{'name': 'Private Name', 'role': 'private@example.com', 'demo': True, 'freeDates': ['private data', '2027-03-20']}])
        self.assertNotIn('Private Name', str(result))
        self.assertNotIn('private@example.com', str(result))
        self.assertEqual(result[0]['freeDates'], ['2027-03-20'])

class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dbpatch = patch.object(server, 'DB_PATH', os.path.join(self.tmp.name, 'test.sqlite'))
        self.dbpatch.start()
        server.initialize()
    def tearDown(self):
        self.dbpatch.stop()
        self.tmp.cleanup()
    def save(self, pack, due='2026-10-10'):
        with server.db() as c:
            c.execute('INSERT INTO runs(id,status,prompt,pack,trace,created_at) VALUES (?,?,?,?,?,?)', ('test-run', 'complete', 'test', json.dumps(pack), '[]', server.now()))
            c.execute('INSERT INTO rechecks(run_id,due,offset) VALUES (?,?,?)', ('test-run', due, 14))
    def pack(self):
        return {'goal': {'location': 'Subang Jaya'}, 'dateDecision': {'chosen': {'date': '2026-10-24'}}, 'drafts': [], 'rechecks': [{'date': '2026-10-10'}]}
    def test_connection_lock_covers_entire_lifetime(self):
        entered = threading.Event()
        completed = threading.Event()
        errors = []
        def reader():
            entered.set()
            try:
                with server.db() as c:
                    c.execute('SELECT COUNT(*) FROM runs').fetchone()
            except Exception as exc:
                errors.append(exc)
            finally:
                completed.set()
        with server.db() as c:
            worker = threading.Thread(target=reader)
            worker.start()
            self.assertTrue(entered.wait(2))
            self.assertFalse(completed.wait(0.05))
            c.execute('SELECT COUNT(*) FROM runs').fetchone()
        worker.join(timeout=5)
        self.assertTrue(completed.is_set())
        self.assertEqual(errors, [])
    def test_failed_connect_releases_lifetime_lock(self):
        with patch.object(server.sqlite3, 'connect', side_effect=server.sqlite3.OperationalError('open failed')):
            with self.assertRaises(server.sqlite3.OperationalError):
                server.db()
        acquired = []
        def probe():
            owns = server.DB_LOCK.acquire(timeout=2)
            acquired.append(owns)
            if owns:
                server.DB_LOCK.release()
        worker = threading.Thread(target=probe)
        worker.start()
        worker.join(timeout=3)
        self.assertEqual(acquired, [True])
    def test_concurrent_read_write_connections_do_not_fail(self):
        from concurrent.futures import ThreadPoolExecutor
        with server.db() as c:
            c.execute('INSERT INTO runs(id,status,prompt,trace,created_at) VALUES (?,?,?,?,?)', ('stress', 'failed', 'test', '[]', server.now()))
        def operation(i):
            with server.db() as c:
                if i % 4:
                    c.execute('UPDATE runs SET status=status WHERE id=?', ('stress',))
                else:
                    c.execute('SELECT trace FROM runs WHERE id=?', ('stress',)).fetchone()
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(operation, range(200)))
        self.assertEqual(server.row_run('stress')['status'], 'failed')
    def test_default_roster_is_empty_and_invalid_type_rejected(self):
        self.assertEqual(public_roster(None), [])
        with self.assertRaises(ValueError):
            public_roster({'name': 'not a list'})
    def test_flat_draft_normalization_order(self):
        p = server.normalize_public_pack({'drafts': {'sponsorEmails': [{'subject': 'a'}], 'followups': [{'subject': 'b'}], 'mc': [{'subject': 'c'}]}, 'metrics': {'trace': ['private duplicate']}})
        self.assertEqual([d['type'] for d in p['drafts']], ['sponsor', 'followup', 'mc'])
        self.assertNotIn('trace', p['metrics'])
    def test_due_low_high_and_unavailable_all_propagate(self):
        for available, probability in [(True, 10), (True, 80), (False, None)]:
            with self.subTest(available=available, probability=probability):
                with server.db() as c:
                    c.execute('DELETE FROM runs')
                    c.execute('DELETE FROM rechecks')
                self.save(self.pack())
                weather = {'available': available, 'date': '2026-10-24', 'rainProbability': probability}
                def update(pack, evidence, emit=None):
                    pack['propagatedWeather'] = evidence
                    return pack
                with patch('src.weather.date_weather', return_value=weather), patch('src.pipeline.apply_weather_update', side_effect=update, create=True) as updater:
                    server.process_due_rechecks('2026-10-10')
                updater.assert_called_once()
                run = server.row_run('test-run')
                self.assertEqual(run['pack']['propagatedWeather'], weather)
                self.assertEqual(run['recheckJobs'][0]['status'], 'complete' if available else 'failed')
    def test_missed_event_does_not_fetch_weather(self):
        pack = self.pack()
        pack['dateDecision']['chosen']['date'] = '2026-10-09'
        self.save(pack)
        with patch('src.weather.date_weather') as fetch:
            server.process_due_rechecks('2026-10-10')
        fetch.assert_not_called()
        self.assertEqual(server.row_run('test-run')['recheckJobs'][0]['status'], 'missed')
    def test_update_failure_never_marked_complete(self):
        self.save(self.pack())
        with patch('src.weather.date_weather', return_value={'available': True}), patch('src.pipeline.apply_weather_update', side_effect=RuntimeError('update failed'), create=True):
            server.process_due_rechecks('2026-10-10')
        self.assertEqual(server.row_run('test-run')['recheckJobs'][0]['status'], 'failed')
    def test_gmail_receipt_schema_has_content_fingerprint(self):
        with server.db() as c:
            columns = {r[1] for r in c.execute('PRAGMA table_info(gmail_receipts)')}
        self.assertIn('content_hash', columns)

    @contextmanager
    def http_server(self):
        with patch.object(server, 'RATE', collections.defaultdict(collections.deque)):
            httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, kwargs={'poll_interval': 0.01})
            thread.start()
            try:
                yield httpd.server_address[1]
            finally:
                httpd.shutdown()
                thread.join(timeout=5)
                httpd.server_close()

    def http_request(self, port, method, path, value=None):
        body = value if isinstance(value, bytes) else json.dumps(value).encode() if value is not None else None
        connection = HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            connection.request(method, path, body=body, headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            raw = response.read()
            payload = json.loads(raw) if response.getheader('Content-Type') == 'application/json' else raw
            return response.status, payload
        finally:
            connection.close()

    def test_queue_submission_failure_returns_503_and_persists_failed_run(self):
        prompt = 'I want to organize a charity event at my university in March with a budget of RM2k.'

        def reject_submission(execute, run_id, submitted_prompt, overrides, roster):
            with server.db() as c:
                row = c.execute('SELECT status,prompt FROM runs WHERE id=?', (run_id,)).fetchone()
            self.assertEqual(row['status'], 'running')
            self.assertEqual(row['prompt'], prompt)
            raise RuntimeError('cannot schedule new futures after shutdown')

        with patch.object(server, 'execute_run') as execute, patch.object(server.POOL, 'submit', side_effect=reject_submission) as submit, self.http_server() as port:
            status, payload = self.http_request(port, 'POST', '/api/runs', {'prompt': prompt})
            self.assertEqual(status, 503)
            self.assertIn('Execution queue unavailable', payload['error'])
            self.assertIn('no successful run is claimed', payload['error'])
            self.assertNotEqual(payload.get('status'), 'complete')
            submit.assert_called_once_with(execute, payload['id'], prompt, {}, [])
            execute.assert_not_called()
            run = server.row_run(payload['id'])
            self.assertEqual(run['status'], 'failed')
            self.assertIn('Execution queue unavailable', run['error'])
            self.assertIsNone(run['pack'])
            self.assertEqual(run['trace'], [])
            self.assertEqual(run['elapsed'], 0)
            self.assertEqual(run['recheckJobs'], [])
            with server.db() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)
                self.assertEqual(c.execute("SELECT COUNT(*) FROM runs WHERE status IN ('running','complete')").fetchone()[0], 0)
            get_status, public_run = self.http_request(port, 'GET', '/api/runs/' + payload['id'])
            self.assertEqual(get_status, 200)
            self.assertEqual(public_run, run)
            stream_status, stream = self.http_request(port, 'GET', '/api/runs/' + payload['id'] + '/stream')
            self.assertEqual(stream_status, 200)
            self.assertIn(b'event: failed\n', stream)
            self.assertNotIn(b'event: complete\n', stream)
            event = json.loads(stream.split(b'data: ', 1)[1].strip())
            self.assertIsNone(event['pack'])
            self.assertEqual(event['error'], run['error'])
            execute.assert_not_called()

    def test_successful_queue_submission_still_returns_202(self):
        prompt = 'I want to organize a charity event at my university in March with a budget of RM2k.'
        with patch.object(server, 'execute_run') as execute, patch.object(server.POOL, 'submit') as submit, self.http_server() as port:
            status, payload = self.http_request(port, 'POST', '/api/runs', {'prompt': prompt})
            self.assertEqual(status, 202)
            self.assertEqual(payload['status'], 'running')
            self.assertNotIn('error', payload)
            submit.assert_called_once_with(execute, payload['id'], prompt, {}, [])
            execute.assert_not_called()
            run = server.row_run(payload['id'])
            self.assertEqual(run['status'], 'running')
            self.assertIsNone(run['error'])
            self.assertIsNone(run['pack'])
            with server.db() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)

    def test_malformed_run_input_rejected_before_insertion_or_submission(self):
        prompt = 'I want to organize a charity event at my university in March with a budget of RM2k.'
        malformed = [
            b'{not json',
            [],
            {},
            {'prompt': '   '},
            {'prompt': 'x' * 3001},
            {'prompt': prompt, 'overrides': ['invalid']},
            {'prompt': prompt, 'overrides': {'month': 13}},
            {'prompt': prompt, 'roster': {'name': 'not a list'}},
        ]
        with patch.object(server, 'execute_run') as execute, patch.object(server.POOL, 'submit') as submit, self.http_server() as port:
            for value in malformed:
                with self.subTest(value=value):
                    status, payload = self.http_request(port, 'POST', '/api/runs', value)
                    self.assertEqual(status, 400)
                    self.assertIn('error', payload)
                    self.assertNotIn('id', payload)
                    with server.db() as c:
                        self.assertEqual(c.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
                    submit.assert_not_called()
                    execute.assert_not_called()

if __name__ == '__main__':
    unittest.main()
