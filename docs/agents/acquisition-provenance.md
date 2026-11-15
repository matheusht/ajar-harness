# Acquisition provenance

This implementation connects signed acquisition routes to the owned laboratory request gate. It does not add target or provider authority.

- The selected environment must declare the acquisition capability. Only a signed acquisition origin may be used; target origins retain their target-account/effect checks, and provider origins cannot be used through this route.
- Acquisition accepts GET and HEAD with a zero-length request body. Credentials, target selectors and duplicate headers are rejected. Known target secrets in raw or percent-decoded acquisition URLs are rejected before recording an intent.
- The host records the admitted grant, environment identity, request identity and transfer outcome. Complete transferred bodies receive a digest; interrupted or unknown bodies do not. An HTTP error, range response or absent HEAD body is not silently treated as a complete successful dependency.
- Original bytes are not rewritten. Acquisition observations are distinct from target mutations and cannot create target-state evidence or satisfy target reset/readback. Unknown transfer outcomes retain cleanup obligations.
- Experiment comparison includes acquisition transfer facts. A changed downloaded body therefore changes the comparison conditions; historical records without acquisition facts remain readable.

The implementation has pure mocked policy/journal tests, including the controller's forwarding method. Those tests do not execute a network request, native runtime or full engagement, and do not establish integration acceptance. Actual acquisition transport, setup repair and target/provider qualification belong to the separately assigned verification work.

Optional capture output manifests from the draft acquisition scenarios are not implemented by this slice. A transfer digest describes received bytes, not proof that a command executed those bytes.
