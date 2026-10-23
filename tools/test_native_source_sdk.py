"""Offline contract checks specified before source adapter implementation.

Run explicitly with python3 -m unittest discover -s tools -p test_native_source_sdk.py.
These checks do not qualify Docker, Go, provider credentials or target behavior.
"""
import copy
import unittest

import native_research as runner


class SourceContract(unittest.TestCase):
    def test_gateway_only_accepts_exact_model_request(self):
        from native_provider_gateway import validate_request
        import json
        path = '/inference/go/openai/v1/chat/completions'
        good = json.dumps({'model': 'deepseek-v4.1-flash', 'messages': [], 'stream': True}).encode()
        validate_request('POST', path, good)
        for method, target, body in [('GET', path, good), ('POST', path + '?x=1', good),
                                     ('POST', '/inference/v1/chat/completions', good),
                                     ('POST', path, b'{"model":"other"}'),
                                     ('POST', path, b'{"model":"deepseek-v4.1-flash","model":"other"}')]:
            with self.assertRaises(ValueError):
                validate_request(method, target, body)

    def test_source_arguments_do_not_require_a_listener(self):
        parser = runner._parser()
        values = ['prepare', '--source-only', '--build-command', '/command.json',
                  '--go-toolchain', 'go1.26.4', '--module-cache', '/modules']
        for name in ('run-root', 'source', 'brief', 'scope-file', 'scope-sha256',
                     'relay', 'relay-sha256', 'runtime-ca', 'runtime-ca-sha256',
                     'image-id', 'target-image-id', 'platform'):
            values.extend(['--' + name, '/placeholder'])
        args = parser.parse_args(values)
        self.assertTrue(args.source_only)
        self.assertIsNone(args.target_port)
        self.assertIsNone(args.target_command)

    def test_paid_route_has_no_free_policy(self):
        plan = {'model': 'opencode-go/deepseek-v4.1-flash',
                'provider_route': 'opencode-go', 'provider_authority': runner.AUTHORITY}
        config = runner._model_config(plan)
        self.assertEqual(config['model'], plan['model'])
        self.assertEqual(config['policies'][-1]['resource'], 'opencode-go')
        self.assertNotIn('fallback', config)
        self.assertNotIn('opencode', [p['resource'] for p in config['policies']])
        for key, value in [('model', runner.MODEL), ('provider_route', 'unknown'),
                           ('provider_authority', 'example.com:443')]:
            bad = dict(plan, **{key: value})
            with self.assertRaises(runner.NativeResearchError):
                runner._model_config(bad)

    def test_service_configuration_stays_equal(self):
        plan = {'model': runner.MODEL, 'provider_route': runner.PROVIDER_ROUTE,
                'provider_authority': runner.AUTHORITY}
        before = copy.deepcopy(runner.CONFIG)
        self.assertEqual(runner._model_config(plan), before)
        self.assertEqual(runner.CONFIG, before)


if __name__ == '__main__':
    unittest.main()
