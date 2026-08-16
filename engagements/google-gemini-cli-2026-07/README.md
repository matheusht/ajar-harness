# google-gemini-cli-2026-07 — disposition records only

The gemini-cli engagement's working records live inside a NESTED GIT CLONE at
`engagements/gemini-cli/engagements/google-gemini-cli-2026-07/`. The outer repository cannot track
files there — git records the nested clone as a gitlink and the contents never leave the machine.

That was discovered on 2026-08-16 when external disposition records written into the nested clone
were silently not committed. Disposition records are the only external ground truth this harness
has, so they must live somewhere the repository can actually see. They live here.

The rest of that engagement's records are still stranded in the nested clone. Moving them out is a
separate cleanup and is not done.
