# Sample data (testing only)

Made-up records for trying the app locally. Not used unless you point the app at them:

    SHELTER_LOG_PATH=data/sample/shelter_log.csv INVENTORY_LOG_PATH=data/sample/inventory_log.csv \
        COMMITMENTS_LOG_PATH=data/sample/commitments_log.csv .venv/bin/python app.py

`shelter_log.csv` covers: an older and a newer validated report (SH-01), a validated
report with a newer pending AI extraction (SH-02), an unknown special-needs count
(SH-03), a shelter with only a pending report (SH-04), and a rejected typo (SH-03).

`inventory_log.csv` covers: general meals in two warehouses (packs and 24-meal cases),
water that is not counted as meals, infant formula and allergy-free special-diet stock,
an older and a newer validated count (WH-B rice), a newer pending count (WH-A bread),
and a rejected typo (WH-A rice).

`commitments_log.csv` covers: a general dispatch from WH-B at 08:45 that WH-B's 10:00
recount already reflects (not subtracted from stock again) and that is shipped but not
confirmed delivered to SH-02; an infant-formula delivery confirmed at SH-01 after its
09:00 report; a general dispatch from WH-A after its 06:30 count; an approved allocation
not yet shipped (reserved); and a cancelled one (ignored).
