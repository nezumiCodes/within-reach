# Synthetic fixtures

Everything here is invented. Client references must start with `SYN-`, and no column may hold
names, NHS numbers or dates of birth. `scripts/check_client_data.py` enforces this on every commit
(spec NFR-06). Real client data never goes in this repository.

Pharmacy codes in these files are placeholders until Phase 1 produces the real directory.
