import os
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
from app.ledger import RuleError
from app.modules.sales.customers import phone_number, phone_key, cipher, details


class CustomerPrivacyTests(unittest.TestCase):
    def test_phone_formats_match_without_guessing_international_numbers(self):
        for phone in ['98765 43210', '+91 (98765) 43210', '09876543210', '91-9876543210']:
            self.assertEqual(phone_number(phone), '+919876543210')
        for phone in ['123', '+44 7700900123', 'abc9876543210', '1234567890']:
            with self.assertRaises(RuleError): phone_number(phone)

    def test_authenticated_encryption_rotation_and_stable_keyed_lookup(self):
        old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        with patch.dict(os.environ, {'KCD_CUSTOMER_ENCRYPTION_KEYS': old, 'KCD_CUSTOMER_LOOKUP_KEY': 'a'*64}):
            token = cipher().encrypt(b'{"name":"Synthetic Customer"}').decode()
            lookup = phone_key('+919876543210')
            self.assertNotIn('Synthetic Customer', token)
        with patch.dict(os.environ, {'KCD_CUSTOMER_ENCRYPTION_KEYS': new+','+old, 'KCD_CUSTOMER_LOOKUP_KEY': 'a'*64}):
            self.assertEqual(details({'id':'x', 'encrypted_details':token})['name'], 'Synthetic Customer')
            self.assertEqual(phone_key('+919876543210'), lookup)
            with self.assertRaises(RuleError): details({'id':'x','encrypted_details':token[:-5]+'xxxxx'})
        with patch.dict(os.environ, {'KCD_CUSTOMER_ENCRYPTION_KEYS':'', 'KCD_CUSTOMER_LOOKUP_KEY':''}):
            with self.assertRaises(RuleError): cipher()
            with self.assertRaises(RuleError): phone_key('+919876543210')
