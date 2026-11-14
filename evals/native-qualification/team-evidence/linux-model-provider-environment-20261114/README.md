# Model provider environment correction — 14 November 2026

Tracing the actual Linux native fixture found that the provider relay supplies both uppercase and lowercase proxy variables, while the model session and private bootstrap accept only their strict uppercase set. The previous contained bridge fixture supplied a simplified map and did not exercise the model admission function. This prevented actual Linux native startup.

The failure-first composition now uses the production `ProxyBridge.environment` and `Session._model_command`. All three composed/reopened scenarios failed with `native_provider_environment_invalid` before the production change. The boundary now selects uppercase entries for the model only; native tools retain both forms, and model/session/bootstrap validation remains strict. All fourteen contained scenario families then passed.

Repeat with Python 3.11+ and `ssh-keygen`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 evals/native-qualification/smoke/check_linux_model_host_e2e.py --output /tmp/linux-model-provider-environment.json
```

Expected: status `passed`, fourteen families. Docker/namespace facts are simulated; protocol/bootstrap subprocesses and the proxy environment/model admission functions are real. This correction is not proof of actual Linux native startup, provider inference or research acceptance. Earlier Linux receipts remain historical evidence of their original source.
