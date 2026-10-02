# Superseded canonical campaign revision 6

Revision 6 is superseded by `behavioral-canonical-v7-2026-10-02` because the gate now reads
`git apply --numstat -z` paths verbatim, preserving filenames that contain arrow delimiters.

Keep revision 6 and its frozen-input hashes unchanged as historical evidence. Revision 7 preserves
the candidate definitions and technique patches while freezing the updated gate and reader; it makes
no execution or efficacy claim.
