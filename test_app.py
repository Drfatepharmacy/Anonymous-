import unittest
import os
import io
import json
from app import app, db, Visit, Message, Admin

class AnonVibeTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SECRET_KEY'] = 'test-secret'
        self.client = app.test_client()
        with app.app_context():
            db.create_all()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_index_route(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'ANON', response.data)

    def test_log_visit(self):
        payload = {
            "fingerprint": "test_fp_12345",
            "fpData": {
                "platform": "Linux x86_64",
                "maxTouchPoints": 0,
                "hardwareConcurrency": 8,
                "deviceMemory": 16
            }
        }
        response = self.client.post('/api/log', json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get('status'), 'success')

        with app.app_context():
            v = Visit.query.filter_by(fingerprint="test_fp_12345").first()
            self.assertIsNotNone(v)
            self.assertEqual(v.platform, "Linux x86_64")

    def test_submit_phone_and_location(self):
        # First create visit
        self.client.post('/api/log', json={"fingerprint": "fp_device_1"})

        # Submit phone
        res_phone = self.client.post('/api/submit-phone', json={
            "fingerprint": "fp_device_1",
            "phone": "+2348000000000"
        })
        self.assertEqual(res_phone.status_code, 200)

        # Submit location
        res_loc = self.client.post('/api/log-location', json={
            "fingerprint": "fp_device_1",
            "lat": 6.5244,
            "lon": 3.3792,
            "accuracy": 15.5
        })
        self.assertEqual(res_loc.status_code, 200)

        with app.app_context():
            v = Visit.query.filter_by(fingerprint="fp_device_1").first()
            self.assertEqual(v.phone, "+2348000000000")
            self.assertEqual(v.precise_lat, 6.5244)

    def test_messaging_flow(self):
        # Send message via HTTP API
        res = self.client.post('/api/send-message', json={
            "fingerprint": "user1_fp",
            "text": "Hello Vercel and Supabase!"
        })
        self.assertEqual(res.status_code, 200)
        msg_data = res.get_json()
        self.assertEqual(msg_data["text"], "Hello Vercel and Supabase!")

        # Retrieve messages via GET
        res_get = self.client.get('/api/messages?after_id=0')
        self.assertEqual(res_get.status_code, 200)
        messages = res_get.get_json()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["text"], "Hello Vercel and Supabase!")

    def test_attachment_upload(self):
        data = {
            'fingerprint': 'user1_fp',
            'file': (io.BytesIO(b"test file content"), 'test.txt')
        }
        res = self.client.post('/api/send-attachment', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        res_data = res.get_json()
        self.assertIn('attachment', res_data)

    def test_admin_auth_and_dashboard(self):
        # Login with default admin credentials
        login_res = self.client.post('/admin/login', data={
            "username": "admin",
            "password": "admin123"
        }, follow_redirects=True)
        self.assertEqual(login_res.status_code, 200)
        self.assertIn(b'CONTROL', login_res.data)

if __name__ == '__main__':
    unittest.main()
