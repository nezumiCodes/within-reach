# Synthetic fixtures

Everything here is invented. Client references must start with `SYN-`, and no column may hold
names, NHS numbers or dates of birth. `scripts/check_client_data.py` enforces this on every commit
(spec NFR-06). Real client data never goes in this repository.

Pharmacy codes in these files are placeholders until Phase 1 produces the real directory.

`fixture_services.csv` gives the app's test release (`app/tests/fixtures/data`) made-up
`services` cells: three English pharmacies near CH2 3JQ list needle exchange (`nsp`), every Welsh
one is not known (`nsp?`). It is not taken from the DoHS API. See `scripts/make_fixture_release.py`.
