import unittest
from collector import classify, handler


class ScopeTests(unittest.TestCase):
    def test_unknown_is_not_absent_or_healthy(self):
        self.assertEqual(classify('inspector2', {'failedAccounts': [{'accountId': 'test'}]}), 'unknown')
        self.assertEqual(classify('cloudtrail', {'trailList': []}), 'unknown')
        self.assertEqual(classify('securitylake', {'dataLakes': []}), 'not_enabled')

    def test_caller_cannot_expand_scope(self):
        for event in [{'action': 'discover', 'region': 'other'}, {'action': 'run_code'}, {'action': 'collect_securityhub', 'MaxResults': 1000}]:
            with self.assertRaises(ValueError):
                handler(event, None)


if __name__ == '__main__':
    unittest.main()
